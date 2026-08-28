**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** CHARACTERISTIC_CURVES — saturation functions and relative permeability functions
**Last verified:** 2026-07-31

# CHARACTERISTIC_CURVES: saturation and relative permeability

## What this block is

A `CHARACTERISTIC_CURVES <name>` block builds one `characteristic_curves_type` object holding **three independent sub-objects**:

| Sub-object | Set by deck keyword | Field |
|---|---|---|
| capillary pressure ↔ saturation | `SATURATION_FUNCTION` | `this%saturation_function` |
| liquid relative permeability | `PERMEABILITY_FUNCTION` (liquid variant) | `this%liq_rel_perm_function` |
| gas relative permeability | `PERMEABILITY_FUNCTION` (gas variant) | `this%gas_rel_perm_function` |

The top-level dispatcher is `CharacteristicCurvesRead` (`src/pflotran/characteristic_curves.F90:77`). It reads one card per loop iteration and switches on the keyword (`src/pflotran/characteristic_curves.F90:119`). `SATURATION_FUNCTION` allocates the concrete saturation type (`src/pflotran/characteristic_curves.F90:121-176`), `PERMEABILITY_FUNCTION` allocates the concrete rel-perm type (`src/pflotran/characteristic_curves.F90:185-352`).

The block is read from the top-level input dispatcher at `src/pflotran/factory_subsurface_read.F90:1627`, which rejects `CHARACTERISTIC_CURVES` for TH-with-freezing, MPH, PNF and NULL flow modes (`src/pflotran/factory_subsurface_read.F90:1628-1648`). The legacy top-level `SATURATION_FUNCTION` card (`src/pflotran/saturation_function.F90:148`) is retired for all other modes: using it outside TH-with-freezing / MPH raises "Must compile with legacy_saturation_function=1" (`src/pflotran/factory_subsurface_read.F90:1610-1614`). **For a normal Richards/general run, `CHARACTERISTIC_CURVES` is the only path.**

Note that inside a `MATERIAL_PROPERTY` block, the keyword `SATURATION_FUNCTION` is merely an *alias* for `CHARACTERISTIC_CURVES` and just names the curve set (`src/pflotran/material.F90:366-369`). That is a different card from the retired top-level one.

---

## 1. van Genuchten saturation function, as implemented

Declared type: `sat_func_vg_type`, carrying exactly two own parameters `alpha` and `m` on top of the base class (`src/pflotran/characteristic_curves_common.F90:35-48`). The base class `sat_func_base_type` supplies `Sr`, `pcmax`, `Sgt_max`, `Sm`, `Pcm` (`src/pflotran/characteristic_curves_base.F90:22-52`).

### 1.1 Saturation from capillary pressure (the forward direction used by the flow solve)

`SFVGSaturation` (`src/pflotran/characteristic_curves_common.F90:889`):

```
n  = 1/(1-m)                                   (:945)
Se = (1 + (alpha*Pc)^n)^(-m)                   (:947, :958)
Sl = Sr + (1-Sr)*Se                            (:961)
```

`Pc <= 0` returns `Sl = 1` (`src/pflotran/characteristic_curves_common.F90:941-943`). A guard returns `Sl = 1` when `(alpha*Pc)^n < 1e-15` to avoid derivative cancellation (`src/pflotran/characteristic_curves_common.F90:917, 952-956`).

### 1.2 Capillary pressure from saturation (inverse)

`SFVGCapillaryPressure` (`src/pflotran/characteristic_curves_common.F90:809`):

```
Se = (Sl - Sr)/(1 - Sr)                        (:863-864)
Pc = (Se^(-1/m) - 1)^(1/n) / alpha             (:867)
```

with clamps: `Sl <= Sr` returns `Pc = pcmax` (`src/pflotran/characteristic_curves_common.F90:852-854`); `Sl >= 1` returns `Pc = 0` (`:855-857`); and a final ceiling `Pc > pcmax → Pc = pcmax, dPc/dSl = 0` (`:880-883`). Gas trapping is a hard error for this type (`:846-850`).

### 1.3 The exact meaning of `M`, and whether `N` is independent

**`N` is derived, never read.** There is no `N` keyword anywhere in the VG read block — the only VG keywords accepted are `M`, `ALPHA`, `LOOP_INVARIANT`, `UNSATURATED_EXTENSION`, `LIQUID_JUNCTION_SATURATION` (`src/pflotran/characteristic_curves.F90:523-544`); any other keyword is a fatal `InputKeywordUnrecognized` (`:541-543`). `n` is recomputed locally as `n = 1/(1-m)` at each of the three evaluation sites: `src/pflotran/characteristic_curves_common.F90:860`, `:945`, `:993`.

So the classical constraint `m = 1 - 1/n` is **hard-wired**, not optional. A calibration layer must sample `m ∈ (0,1)` and must NOT attempt to set `n` independently.

The one exception is the loop-invariant path (§5), where `n` is precomputed once and its formula depends on an internal `rpf` selector: `rpf=1` (Mualem) → `n = 1/(1-m)`; `rpf=2` (Burdine) → `n = 2/(1-m)` (`src/pflotran/characteristic_curves_loop_invariant.F90:490-497`). That selector is hard-set to `1` and there is **no deck keyword to change it** — `vg_rpf_opt = 1 ! Mualem. Burdine option in progress` (`src/pflotran/characteristic_curves.F90:413`), used only at `:1016`. So in practice `n = 1/(1-m)` in both paths.

### 1.4 `ALPHA` units

`ALPHA` is **inverse pressure, Pa⁻¹**, not m⁻¹. Three independent lines of evidence:

1. Dimensional analysis of `src/pflotran/characteristic_curves_common.F90:867`: `Pc = (…)^(1/n) / alpha`, and `Pc` is in Pa everywhere (the input record prints `soil reference pressure … Pa`, `src/pflotran/material.F90:2628`; `DEFAULT_PCMAX = 1.d9` Pa, `src/pflotran/characteristic_curves_base.F90:11`).
2. The WIPP error message calls it exactly that: "you must specify ALPHA (inverse of the threshold capillary pressure)" (`src/pflotran/characteristic_curves.F90:1058-1063`).
3. Regression decks use `ALPHA 1.d-4` with `M 0.5d0` — 1e-4 Pa⁻¹ ≈ 0.98 m⁻¹ of water head, a physically ordinary sandy value.

`ALPHA` is read raw with `InputReadDouble` and **no unit conversion is applied** (`src/pflotran/characteristic_curves.F90:529-532`) — contrast `ROCK_DENSITY`, which does call `InputReadAndConvertUnits` (`src/pflotran/material.F90:379-380`). There is no way to give `ALPHA` in m⁻¹.

### 1.5 `LIQUID_RESIDUAL_SATURATION` in the saturation block

Read at `src/pflotran/characteristic_curves.F90:485-488` into `saturation_function%Sr`. Initialized to `UNINITIALIZED_DOUBLE` (`src/pflotran/characteristic_curves_base.F90:123`) and **required**: `SFBaseVerify` raises a fatal error if still uninitialized (`src/pflotran/characteristic_curves_base.F90:147-151`). `ALPHA` and `M` are likewise required by `SFVGVerify` (`src/pflotran/characteristic_curves_common.F90:796-803`).

Semantically it is the lower clamp of the Se normalization, `Se = (Sl - Sr)/(1 - Sr)` — it shifts and rescales the whole retention curve.

---

## 2. THE CRITICAL QUESTION: are `M` and `LIQUID_RESIDUAL_SATURATION` shared across the three blocks?

**No. They are three genuinely independent variables. All three must be set. Nothing propagates, overrides, or validates one against another.**

### 2.1 Separate storage

- `sat_func_base_type%Sr` — one field, on the saturation object (`src/pflotran/characteristic_curves_base.F90:25`).
- `rel_perm_func_base_type%Sr` — a *different* field, on each rel-perm object (`src/pflotran/characteristic_curves_base.F90:59`).
- `sat_func_vg_type%m` (`src/pflotran/characteristic_curves_common.F90:37`), `rpf_mualem_vg_liq_type%m` (`:149`), and `rpf_mualem_vg_gas_type%m` (`:160`) are three separate component declarations on three separate derived types.

### 2.2 Separate reads

The `LIQUID_RESIDUAL_SATURATION` card appears twice in the source, in two different readers, writing to two different objects:

- `src/pflotran/characteristic_curves.F90:485-488` → `saturation_function%Sr`
- `src/pflotran/characteristic_curves.F90:1237-1240` → `permeability_function%Sr`

`M` appears in the saturation reader (`:525-528` → `sf%m`) and again, separately, in each rel-perm reader (`:1259-1262` → liquid `rpf%m`; `:1273-1276` → gas `rpf%m`).

Each `PERMEABILITY_FUNCTION` block invokes `PermeabilityFunctionRead` once against its own freshly-allocated object (`src/pflotran/characteristic_curves.F90:326-336`), so the liquid block and the gas block never see each other's values.

### 2.3 Separate, independent requirement checks

- Saturation function: `Sr` required (`characteristic_curves_base.F90:147-151`), `ALPHA` and `M` required (`characteristic_curves_common.F90:796-803`).
- `MUALEM_VG_LIQ`: `Sr` required via `RPFBaseVerify` (`characteristic_curves_base.F90:191-195`), `M` required (`characteristic_curves_common.F90:3162-3165`).
- `MUALEM_VG_GAS`: `Sr` required via `RPFBaseVerify`, and `GAS_RESIDUAL_SATURATION` required (`characteristic_curves_common.F90:3357-3360`).

### 2.4 The one cross-check exists but is DEAD CODE

`CharacteristicCurvesVerify` contains the only comparison between the two `Sr` values:

```fortran
    if (characteristic_curves%saturation_function%Sr < &
        characteristic_curves%liq_rel_perm_function%Sr) then
        option%io_buffer = 'The saturation function residual is below the &
                           & liquid relative permeability residual. This  &
                           & may cause numerical instability if capillary &
                           & pressure is not defined below residual.'
    end if
```
(`src/pflotran/characteristic_curves.F90:2355-2365`)

It assigns `option%io_buffer` and **never calls `PrintWrnMsg` or `PrintErrMsg`**, so the message is silently discarded. (The same defect appears at `:2320-2328`, where a missing saturation function sets `io_buffer` with no print call.) Contrast the live checks in the same routine at `:2338` and `:2351`, which do call `PrintErrMsg`.

**Consequence for calibration:** inconsistent residual saturations across the three blocks are accepted without any diagnostic. If a calibration layer perturbs `LIQUID_RESIDUAL_SATURATION` it must perturb it in **all three places simultaneously** unless the intent is genuinely to decouple the retention residual from the relative-permeability residual. Same for `M`.

### 2.5 Which `Sr` do downstream consumers actually see?

`CharCurvesGetGetResidualSats` returns the **relative-permeability** residuals, not the saturation function's: element 1 is `characteristic_curves%liq_rel_perm_function%Sr` (`src/pflotran/characteristic_curves.F90:2119-2120`), and the gas element is the gas rel-perm function's `Srg` (or `Sr`, per concrete class) (`:2126-2140`). So a code path asking "what is the residual liquid saturation of this material" gets the `PERMEABILITY_FUNCTION` value, not the `SATURATION_FUNCTION` value.

### 2.6 Uninitialized-`m` hazard in `MUALEM_VG_GAS`

`RPFMualemVGGasInit` calls `RPFBaseInit` and sets `analytical_derivative_available` — it does **not** set `this%m = UNINITIALIZED_DOUBLE` (`src/pflotran/characteristic_curves_common.F90:3322-3335`), unlike the liquid variant which does (`:3136`). `RPFMualemVGGasVerify` checks only `Srg` (`:3357-3360`). Therefore **omitting `M` from a `MUALEM_VG_GAS` block is not caught** and `this%m` is whatever the allocation left in memory, then used at `:3409`. Always set `M` explicitly in the gas block.

---

## 3. Relative permeability functions

### 3.1 Registry (name → concrete type → implied phase)

Dispatch table at `src/pflotran/characteristic_curves.F90:191-336`. Selected entries relevant to VG calibration:

| Deck keyword | Line | Implied `PHASE` |
|---|---|---|
| `MUALEM`, `MUALEM_VG_LIQ` | `:192-194` | `LIQUID` |
| `MUALEM_VG_GAS` | `:195-197` | `GAS` |
| `BURDINE`, `BURDINE_BC_LIQ` | `:198-200` | `LIQUID` |
| `BURDINE_VG_LIQ` | `:216-218` | `LIQUID` |
| `BURDINE_VG_GAS` | `:219-221` | `GAS` |
| `MUALEM_BC_LIQ` / `MUALEM_BC_GAS` | `:210-215` | `LIQUID` / `GAS` |
| `CONSTANT` | `:312-314` | none — `PHASE` card required |
| `TABLE_LIQ` / `TABLE_GAS` | `:306-311` | `LIQUID` / `GAS` |

`MUALEM` is a bare alias for `MUALEM_VG_LIQ` — same object, same required cards. Functions whose keyword does not imply a phase leave `phase_keyword = 'NONE'` and then require an explicit `PHASE` card, else fatal (`:1926-1935`). The resolved phase decides whether the object lands in `liq_rel_perm_function` or `gas_rel_perm_function` (`:338-343`).

### 3.2 Mualem–van Genuchten, liquid

`RPFMualemVGLiqRelPerm` (`src/pflotran/characteristic_curves_common.F90:3212`):

```
Se = (Sl - Sr)/(1 - Sr)                                      (:3246)
Kr = sqrt(Se) * ( 1 - (1 - Se^(1/m))^m )^2                   (:3266)
```

with `Se >= 1 → Kr = 1` and `Se <= 0 → Kr = 0` (`:3247-3253`). Note the `sqrt` — the Mualem pore-connectivity exponent is **hard-coded at 0.5** and is not a deck parameter here.

Read block accepts only `M` and `LOOP_INVARIANT`, plus the base cards `LIQUID_RESIDUAL_SATURATION`, `PHASE`, `SMOOTH`, `SPLINE` (`src/pflotran/characteristic_curves.F90:1236-1269`).

### 3.3 Mualem–van Genuchten, gas

`RPFMualemVGGasRelPerm` (`src/pflotran/characteristic_curves_common.F90:3366`):

```
Se  = (Sl - Sr)/(1 - Sr - Srg)                               (:3395)
Seg = 1 - Se                                                 (:3408)
Kr  = sqrt(Seg) * (1 - Se^(1/m))^(2m)                        (:3409)
```

Note the denominator `1 - Sr - Srg` differs from the liquid form's `1 - Sr`. Limits are inverted relative to the liquid function: `Se >= 1 → Kr = 0`, `Se <= 0 → Kr = 1` (`:3400-3406`).

Read block accepts `M`, `GAS_RESIDUAL_SATURATION`, `LOOP_INVARIANT` (`src/pflotran/characteristic_curves.F90:1271-1287`).

### 3.4 Burdine–van Genuchten (available, different exponents)

Liquid, `RPFBurdineVGLiqRelPerm` (`src/pflotran/characteristic_curves_common.F90:4696`):
```
Kr = Se^2 * ( 1 - (1 - Se^(1/m))^m )                         (:4750)
```
Gas, `RPFBurdineVGGasRelPerm` (`:4820`):
```
Kr = Seg^2 * ( 1 - Se^(1/m) )^m                              (:4863)
```
Using `BURDINE_VG_LIQ` without `SMOOTH` emits a warning (`src/pflotran/characteristic_curves.F90:1983-1988`).

### 3.5 What `SMOOTH` does

`SMOOTH` is a bare flag (no value) that sets a local `smooth = PETSC_TRUE` (`src/pflotran/characteristic_curves.F90:1245-1246`); at end of block it calls `permeability_function%SetupPolynomials` (`:1960-1962`).

For `MUALEM_VG_LIQ` that dispatches to `RPFMualemVGSetupPolynomials` (`src/pflotran/characteristic_curves_common.F90:3171`), which fits a **cubic polynomial on `Se ∈ [0.99, 1.0]`** (`:3190-3191`) matched to value and slope at both ends (`:3196-3204`). At runtime, when `Se > poly%low` the polynomial is evaluated instead of the analytic form (`:3255-3261`). Purpose: remove the near-saturation kink where `dKr/dSe` blows up, which is a real Newton-convergence problem — hence the warning printed when `MUALEM_VG_LIQ` is used **without** `SMOOTH` (`src/pflotran/characteristic_curves.F90:1989-1994`).

Two hard gotchas:

- **`SMOOTH` on `MUALEM_VG_GAS` is a fatal error.** `rpf_mualem_vg_gas_type` binds only `Init`, `Verify`, `RelativePermeability` (`src/pflotran/characteristic_curves_common.F90:159-165`) — it does not override `SetupPolynomials`, so the call falls through to `RPFBaseSetupPolynomials`, which prints "RPF Smoothing not supported for …" via `PrintErrMsg` (`src/pflotran/characteristic_curves_base.F90:281-296`).
- **`SMOOTH` inside `SATURATION_FUNCTION VAN_GENUCHTEN` is also a fatal error.** `sat_func_vg_type` binds no `SetupPolynomials` (`characteristic_curves_common.F90:38-47`), so the `smooth` branch at `characteristic_curves.F90:1032-1034` reaches `SFBaseSetupPolynomials` → `PrintErrMsg` (`characteristic_curves_base.F90:208-223`). (Brooks–Corey *does* support it and warns when it is absent, `characteristic_curves.F90:1050-1055`.)

`SMOOTH` is therefore a `PERMEABILITY_FUNCTION`-only, liquid-VG/BC-only card in this build. It is a **numerical** switch, not a physical parameter: it perturbs `Kr` only over `Se ∈ (0.99, 1)`.

### 3.6 `SPLINE` and `PCHIP`

`SPLINE <int>` (`src/pflotran/characteristic_curves.F90:1247-1249`) replaces the analytic function with an `n`-point PCHIP interpolant built from it, `RPFPCHIPCtorFunction` (`:1964-1979`). Same idea on the saturation side. This is a speed/robustness knob, not a fitting parameter.

---

## 4. Base cards common to every `SATURATION_FUNCTION`

Read before the type-specific switch (`src/pflotran/characteristic_curves.F90:484-504`):

| Card | Target | Default | Line |
|---|---|---|---|
| `LIQUID_RESIDUAL_SATURATION` | `sf%Sr` | none, **required** | `:485-488` |
| `MAX_CAPILLARY_PRESSURE` | `sf%Pcmax` | `1.d9` Pa | `:489-492`, default `characteristic_curves_base.F90:11,124` |
| `MAX_TRAPPED_GAS_SAT` | `sf%Sgt_max` | `UNINITIALIZED_DOUBLE` | `:493-496`, `characteristic_curves_base.F90:125` |
| `SMOOTH` | flag | off | `:497-498` (fatal for VG, see §3.5) |
| `SPLINE` | int | 0 | `:499-501` |

Common `PERMEABILITY_FUNCTION` base cards (`src/pflotran/characteristic_curves.F90:1236-1252`): `LIQUID_RESIDUAL_SATURATION`, `PHASE`, `SMOOTH`, `SPLINE`.

---

## 5. `LOOP_INVARIANT` — the only place parameter ranges are validated

`LOOP_INVARIANT` (a bare flag) causes the read routine to discard the object it just filled and rebuild it via a constructor that precomputes every `m`-derived quantity once (`src/pflotran/characteristic_curves.F90:533-534, 1876-1922`; e.g. `RPFMVGliqCtor` at `characteristic_curves_loop_invariant.F90:1562`).

Those constructors are the **only** place PFLOTRAN range-checks these parameters:

- `SFVGConfigure` (`src/pflotran/characteristic_curves_loop_invariant.F90:459`): `alpha <= 0` → error bit 1; `m <= 0 or m >= 1` → bit 2; `Sr < 0 or Sr >= 1` → bit 4 (`:476-479`).
- `RPFVGliqConfigure` (`:1496`): `m <= 0 or m >= 1` → bit 1; `Sr < 0 or Sr >= 1` → bit 2 (`:1506-1507`).

**Without `LOOP_INVARIANT` there is no bounds checking at all.** A deck with `M 1.5` or a negative `ALPHA` is accepted by the ordinary path and produces NaNs or garbage downstream. A calibration layer sampling `M` and `ALPHA` should either enforce `0 < m < 1`, `alpha > 0`, `0 <= Sr < 1` itself, or turn on `LOOP_INVARIANT` to get the guard for free.

`UNSATURATED_EXTENSION` requires `LOOP_INVARIANT`; using it without is fatal (`src/pflotran/characteristic_curves.F90:1025-1030`).

---

## 6. Calibration-knobs summary

Ranges marked "enforced" are checked in source under `LOOP_INVARIANT` (§5); the others are physical guidance, not code-enforced.

| Deck keyword | Block | Source line | Units | Default | Valid range | Controls |
|---|---|---|---|---|---|---|
| `M` | `SATURATION_FUNCTION VAN_GENUCHTEN` | `characteristic_curves.F90:525-528` | – | none, **required** (`characteristic_curves_common.F90:800-803`) | `0 < m < 1` (enforced `characteristic_curves_loop_invariant.F90:477`) | retention-curve sharpness; `n = 1/(1-m)` derived |
| `ALPHA` | `SATURATION_FUNCTION VAN_GENUCHTEN` | `characteristic_curves.F90:529-532` | **Pa⁻¹** | none, **required** (`characteristic_curves_common.F90:796-799`) | `alpha > 0` (enforced `characteristic_curves_loop_invariant.F90:476`) | inverse air-entry pressure; scales `Pc` (`characteristic_curves_common.F90:867`) |
| `LIQUID_RESIDUAL_SATURATION` | `SATURATION_FUNCTION` | `characteristic_curves.F90:485-488` | – | none, **required** (`characteristic_curves_base.F90:147-151`) | `0 <= Sr < 1` (enforced `characteristic_curves_loop_invariant.F90:478`) | lower clamp of retention `Se` |
| `MAX_CAPILLARY_PRESSURE` | `SATURATION_FUNCTION` | `characteristic_curves.F90:489-492` | Pa | `1.d9` (`characteristic_curves_base.F90:11`) | > 0 | `Pc` ceiling (`characteristic_curves_common.F90:880-883`) |
| `MAX_TRAPPED_GAS_SAT` | `SATURATION_FUNCTION` | `characteristic_curves.F90:493-496` | – | uninitialized | `[0,1)` | max trapped gas; **fatal for plain VG** (`characteristic_curves_common.F90:846-850`) |
| `M` | `PERMEABILITY_FUNCTION MUALEM_VG_LIQ` | `characteristic_curves.F90:1259-1262` | – | none, **required** (`characteristic_curves_common.F90:3162-3165`) | `0 < m < 1` (enforced `characteristic_curves_loop_invariant.F90:1506`) | liquid `Kr` shape (`characteristic_curves_common.F90:3266`) |
| `LIQUID_RESIDUAL_SATURATION` | `PERMEABILITY_FUNCTION` (any) | `characteristic_curves.F90:1237-1240` | – | none, **required** (`characteristic_curves_base.F90:191-195`) | `0 <= Sr < 1` (enforced `characteristic_curves_loop_invariant.F90:1507`) | `Kr` `Se` normalization; also what `CharCurvesGetGetResidualSats` reports (`characteristic_curves.F90:2118-2119`) |
| `SMOOTH` | `PERMEABILITY_FUNCTION MUALEM_VG_LIQ` | `characteristic_curves.F90:1245-1246` | flag | off (warns if absent, `:1989-1994`) | on/off | cubic patch on `Se ∈ [0.99,1]` (`characteristic_curves_common.F90:3190-3204`) |
| `M` | `PERMEABILITY_FUNCTION MUALEM_VG_GAS` | `characteristic_curves.F90:1273-1276` | – | **not defaulted, not verified** (§2.6) | `0 < m < 1` | gas `Kr` shape (`characteristic_curves_common.F90:3409`) |
| `GAS_RESIDUAL_SATURATION` | `PERMEABILITY_FUNCTION MUALEM_VG_GAS` | `characteristic_curves.F90:1277-1280` | – | none, **required** (`characteristic_curves_common.F90:3357-3360`) | `0 <= Srg`, `Sr+Srg < 1` | widens `Kr` denominator `1-Sr-Srg` (`characteristic_curves_common.F90:3395`) |
| `PHASE` | `PERMEABILITY_FUNCTION` | `characteristic_curves.F90:1241-1244` | `LIQUID`/`GAS` | implied by function name | – | which slot the object fills |
| `LOOP_INVARIANT` | either block | `characteristic_curves.F90:533-534`, `:1263-1264` | flag | off | on/off | precompute + **enables range validation** |
| `SPLINE` | either block | `characteristic_curves.F90:499-501`, `:1247-1249` | int | 0 | > 0 | replace analytic curve with PCHIP interpolant |

### Minimal well-formed VG two-phase set

```
CHARACTERISTIC_CURVES sf1
  SATURATION_FUNCTION VAN_GENUCHTEN
    M <m_sat>
    ALPHA <1/Pa>
    LIQUID_RESIDUAL_SATURATION <Sr_sat>
  /
  PERMEABILITY_FUNCTION MUALEM_VG_LIQ
    M <m_liq>
    LIQUID_RESIDUAL_SATURATION <Sr_liq>
    SMOOTH
  /
  PERMEABILITY_FUNCTION MUALEM_VG_GAS
    M <m_gas>
    LIQUID_RESIDUAL_SATURATION <Sr_gas>
    GAS_RESIDUAL_SATURATION <Srg>
  /
END
```

`<m_sat>`, `<m_liq>`, `<m_gas>` and `<Sr_sat>`, `<Sr_liq>`, `<Sr_gas>` are six independent numbers as far as the code is concerned (§2). Physically consistent decks set `m_sat = m_liq = m_gas` and `Sr_sat = Sr_liq = Sr_gas`; a calibration layer that treats `M` and `LIQUID_RESIDUAL_SATURATION` as two calibrated scalars must broadcast each to all of its occurrences.

---

## Related

- `material_property_card.md` — how a `MATERIAL_PROPERTY` binds to a named `CHARACTERISTIC_CURVES` set, and every other material card.
- `porosity_permeability_evolution.md` — `PERMEABILITY_POWER` / `PERMEABILITY_CRITICAL_POROSITY` / `PERMEABILITY_MIN_SCALE_FACTOR`.
