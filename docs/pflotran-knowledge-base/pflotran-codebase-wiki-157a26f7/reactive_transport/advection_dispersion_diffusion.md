**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** reactive transport — hydrodynamic dispersion, molecular diffusion, tortuosity, upwinded advection
**Last verified:** 2026-07-31

---

# Advection, dispersion and diffusion in the GIRT/OSRT transport operator

Everything on this page lives in `src/pflotran/transport.F90` (the kernels) and
`src/pflotran/reactive_transport.F90` (the drivers that walk the connection sets and call
them). Parameter *input* is split across `material.F90` (per-material dispersivity and
tortuosity), `fluid.F90` (per-phase diffusion coefficient), and `reaction.F90` (per-species
diffusion coefficients).

> **PETSc is external.** `VecGetArrayF90`, `MatSetValuesLocal`, `VecShift`, `VecMax` and the
> `Vec`/`Mat` types are PETSc library calls and types, not PFLOTRAN code.

---

## 1. The transport coefficient pipeline

Per time step (GIRT: `PMRTPreSolve`, `src/pflotran/pm_rt.F90:722-725`; OSRT: both
`PMOSRTPreSolve` at `src/pflotran/pm_osrt.F90:190` and again inside the retry loop at
`src/pflotran/pmc_subsurface_osrt.F90:288`) the driver calls:

```
RTUpdateTransportCoefs(realization)        reactive_transport.F90:1169
   ├── interior connections  → TDispersion    → patch%internal_tran_coefs
   └── boundary connections  → TDispersionBC  → patch%boundary_tran_coefs
```
(`src/pflotran/reactive_transport.F90:1262-1353`)

Then, per residual evaluation (GIRT) or per matrix assembly (OSRT), those stored coefficients
are combined with the Darcy velocity into upwinded face coefficients:

```
TFluxCoef    (interior)   transport.F90:520     → T_up, T_dn
TFluxCoefBC  (boundary)   transport.F90:604     → T_up, T_dn
TFlux        (residual)   transport.F90:403     → Flux, Res
```

Called from `RTResidualFlux` (`src/pflotran/reactive_transport.F90:2285-2300, 2357-2371`) for
GIRT and from `RTCalculateTransportMatrix` / `RTCalculateRHS_t1`
(`src/pflotran/reactive_transport.F90:1677-1686, 1725-1732, 1451-1459`) for OSRT.

There is a deliberate comment that transport coefficients are **never** evaluated at time level
$k$: `! geh: never use transport coefs evaluated at time k`
(`src/pflotran/reactive_transport.F90:877-878`) — the call is commented out in
`RTInitializeTimestep`.

---

## 2. `TDispersion` — the hydrodynamic dispersion coefficient

`TDispersion` (`src/pflotran/transport.F90:52-251`) produces, for each phase and each diffusion
coefficient index, a **single harmonically averaged coefficient divided by the inter-cell
distance**. Its own header states the intent
(`src/pflotran/transport.F90:58-63`).

The per-side hydrodynamic dispersion is
(`src/pflotran/transport.F90:232-243`):

$$
D^{\text{hyd}}_{\alpha} \;=\; \max\!\Big(\,\underbrace{D^{\text{mech}}_{\alpha}}_{\S 2.2}
\;+\; \epsilon_\alpha\, S_\alpha\, \phi_\alpha\, \tau_\alpha\, D^{m}_{\alpha},\; 10^{-40}\Big)
$$

where $\epsilon$ is the secondary-continuum volume fraction (1 unless `MULTIPLE_CONTINUUM`;
`src/pflotran/transport.F90:236, 241` and `src/pflotran/reactive_transport.F90:1231-1232,
1289-1292`), $S$ is phase saturation, $\phi$ porosity, $\tau$ tortuosity, $D^m$ the molecular
diffusion coefficient. The floor of `1.d-40` prevents a zero denominator downstream.

The two sides are then harmonically averaged and divided by distance
(`src/pflotran/transport.F90:244-248`):

$$
\frac{D^{\text{hyd}}}{\Delta x}\bigg|_{\text{face}}
=\frac{D^{\text{hyd}}_{up}\,D^{\text{hyd}}_{dn}}
      {D^{\text{hyd}}_{up}\,\Delta x_{dn} + D^{\text{hyd}}_{dn}\,\Delta x_{up}}
$$

with $\Delta x_{up},\Delta x_{dn}$ from `ConnectionCalculateDistances`
(`src/pflotran/transport.F90:121-123`).

**Dry-cell skip.** A phase is skipped entirely on a connection if either side's saturation is
below `rt_min_saturation` (`src/pflotran/transport.F90:124-128`); the coefficient array was
zeroed at entry (`src/pflotran/transport.F90:119`), so the connection contributes no dispersive
flux for that phase.

### 2.1 Molecular diffusion and its temperature dependence

The base value is `rt_parameter%diffusion_coefficient(:,iphase)`
(`src/pflotran/transport.F90:129-130`). If `temperature_dependent_diffusion` is on
(`src/pflotran/transport.F90:131`):

- **Liquid phase** — Arrhenius scaling about $T_{\text{ref}} = 25\,^\circ\mathrm{C}$
  (`PetscReal, parameter :: TREF = 25.d0`, `src/pflotran/transport.F90:111`), using the
  per-coefficient activation energy (`src/pflotran/transport.F90:133-143`).
- **Gas phase** — an empirical pressure/temperature scaling
  (`src/pflotran/transport.F90:144-154`):

$$
D^m_g \;\leftarrow\; D^m_g \left(\frac{T + 273.15}{273.15}\right)^{1.8}
\frac{P_{\text{ref}}}{P_g},\qquad P_{\text{ref}} = 101325\ \mathrm{Pa}
$$

  (`PREF = 101325.d0` at `src/pflotran/transport.F90:110`; `T273K` is the freezing-point
  constant). The in-source comment notes this assumes `%pres(GAS_PHASE)` holds *total*
  pressure (`src/pflotran/transport.F90:145-146`).

### 2.2 Mechanical dispersion

Two branches, selected by `rt_parameter%calculate_transverse_dispersion`
(`src/pflotran/transport.F90:175`):

**(a) Longitudinal only (the default).** When no material declares a transverse dispersivity:

$$
D^{\text{mech}} = \alpha_L \, |q|
$$

(`src/pflotran/transport.F90:228-230`), with $q$ the face-normal Darcy flux
`qdarcy(iphase)` (`src/pflotran/transport.F90:174`).

**(b) Full tensor.** When any material has a nonzero transverse dispersivity, PFLOTRAN builds
the classical Scheidegger-type dispersion tensor from a *cell-centered* velocity vector
reconstructed by `PatchGetCellCenteredVelocities` and blended with the face flux
(`src/pflotran/transport.F90:176-179`):

$$
\mathbf{v} = q\,|\hat{d}| + (1 - |\hat{d}|)\,\mathbf{v}_{\text{cell}}
$$

then, with $v = \|\mathbf{v}\|$ (`src/pflotran/transport.F90:180-199`):

$$
D_{xx} = \alpha_L\frac{v_x^2}{v} + \alpha_{TH}\frac{v_y^2}{v} + \alpha_{TV}\frac{v_z^2}{v}
$$
$$
D_{yy} = \alpha_{TH}\frac{v_x^2}{v} + \alpha_{L}\frac{v_y^2}{v} + \alpha_{TV}\frac{v_z^2}{v}
$$
$$
D_{zz} = \alpha_{TV}\frac{v_x^2}{v} + \alpha_{TV}\frac{v_y^2}{v} + \alpha_{L}\frac{v_z^2}{v}
$$

(`src/pflotran/transport.F90:200-222`), projected onto the connection's unit direction vector
(`src/pflotran/transport.F90:223-227`):

$$
D^{\text{mech}} = \max\!\big(d_1^2 D_{xx} + d_2^2 D_{yy} + d_3^2 D_{zz},\ 10^{-40}\big)
$$

> **Caveat as coded.** The $D_{yy}$ and $D_{zz}$ expressions are not symmetric in the way the
> textbook Burnett-Frind form is: $D_{zz}$ uses $\alpha_{TV}$ for *both* the $x$ and $y$
> contributions (`src/pflotran/transport.F90:216-222`), whereas $D_{yy}$ uses $\alpha_{TH}$ for
> $x$ and $\alpha_{TV}$ for $z$. This is what the source does; it is stated here without
> judgment because there is no in-source comment explaining the choice.
>
> Also note `TDispersionBC` divides by `v_dn` **without** the `v > 0` guard that `TDispersion`
> has (compare `src/pflotran/transport.F90:181-189` with
> `src/pflotran/transport.F90:356-359`) — a stagnant boundary cell with transverse dispersivity
> enabled would divide by zero there. Not verifiable statically whether any deck reaches it.

### 2.3 Tortuosity

Two mutually exclusive representations:

- **Scalar** — `tort = material_auxvar%tortuosity` (`src/pflotran/transport.F90:170-172`).
- **Anisotropic** — `TortuosityTensorToScalar(material_auxvar, dist)` projects a
  $(\tau_x,\tau_y,\tau_z)$ tensor onto the connection direction
  (`src/pflotran/transport.F90:167-169`; the function lives at
  `src/pflotran/material_aux.F90:728-751`). Enabled by the `ANISOTROPIC_TORTUOSITY` block
  (`src/pflotran/material.F90:479-481`), which sets
  `option%transport%anisotropic_tortuosity` and is copied into the transport parameter struct
  at `src/pflotran/reactive_transport.F90:186`.

`material.F90` enforces the exclusivity: specifying both `TORTUOSITY` and
`ANISOTROPIC_TORTUOSITY` in one `MATERIAL_PROPERTY` is fatal
(`src/pflotran/material.F90:1132-1140`), and if `ANISOTROPIC_TORTUOSITY` is used anywhere then
all three of `TORTUOSITY_X/_Y/_Z` must be defined in every material
(`src/pflotran/material.F90:1141-1151`). `RTSetup` additionally warns on non-initialized
tortuosity per cell (`src/pflotran/reactive_transport.F90:207-219`).

---

## 3. Millington-Quirk tortuosity

`USE_MILLINGTON_QUIRK_TORTUOSITY` in the `SUBSURFACE_TRANSPORT` `OPTIONS` block
(`src/pflotran/pm_rt.F90:237-238`) sets `rt_parameter%millington_quirk_tortuosity`
(`src/pflotran/pm_rt.F90:434-436`). Its **only** effect in the transport kernels is to
multiply the molecular diffusion coefficient in place, *before* the ordinary tortuosity factor
is applied:

```fortran
  PetscReal, parameter :: s_pow = 7.d0/3.d0
  PetscReal, parameter :: por_pow = 1.d0/3.d0
  ...
    if (rt_parameter%millington_quirk_tortuosity) then
      molecular_diffusion_up(:) = &
            molecular_diffusion_up(:) * &
            sat_up**s_pow * &
            material_auxvar_up%porosity**por_pow
```
(`src/pflotran/transport.F90:113-114, 157-166`; the boundary counterpart, using the
*downstream* cell's saturation and porosity, is `src/pflotran/transport.F90:308-309, 341-346`.)

So the effective coefficient that enters $D^{\text{hyd}}$ becomes

$$
\epsilon\,S\,\phi\,\tau\,\Big(S^{7/3}\,\phi^{1/3}\,D^m\Big)
\;=\;\epsilon\,\tau\,S^{10/3}\,\phi^{4/3}\,D^m
$$

because `TDispersion` already multiplies by $S\,\phi\,\tau$ at
`src/pflotran/transport.F90:234-243`. **The Millington-Quirk factor is applied on top of, not
instead of, the $S\phi$ scaling.**

**What the default is when the card is absent.** `millington_quirk_tortuosity` defaults to
`PETSC_FALSE` in both the process model (`src/pflotran/pm_rt.F90:156`) and the parameter struct
(`src/pflotran/reactive_transport_aux.F90:192`). The diffusive term is then simply
$\epsilon S \phi \tau D^m$, where $\tau$ is whatever `TORTUOSITY` the material declares —
default `1.d0` (`src/pflotran/material.F90:209`).

**Hard guard.** With the card on, every cell's `TORTUOSITY` must be exactly 1. `PMRTSetup`
checks this with PETSc `VecShift(-1)` / `VecAbs` / `VecMax` and aborts if the max deviation
exceeds `1.d-40`:

> `TORTUOSITY must be set to the default value of 1 in MATERIAL_PROPERTY when using USE_MILLINGTON_QUIRK_TORTUOSITY.`

(`src/pflotran/pm_rt.F90:469-484`). This makes Millington-Quirk and a user-supplied constant
tortuosity mutually exclusive.

**Third tortuosity option (independent of the above).**
`TORTUOSITY_FUNCTION_OF_POROSITY <power>` in `MATERIAL_PROPERTY`
(`src/pflotran/material.F90:518-523`) sets `tortuosity = porosity**power`
(`src/pflotran/material.F90:1032-1033`) and marks `tortuosity` uninitialized at read time.
This is incompatible with a `TORTUOSITY` dataset (`src/pflotran/material.F90:1027-1028`) and,
because it yields $\tau \ne 1$, would also trip the Millington-Quirk guard.

---

## 4. Dispersivity input — where `LONGITUDINAL_DISPERSIVITY` lives

Despite being a transport parameter, dispersivity is read in **`material.F90`**, inside
`MATERIAL_PROPERTY` (`src/pflotran/material.F90:386-394`):

| Deck keyword | Stored in | Line |
|---|---|---|
| `LONGITUDINAL_DISPERSIVITY <real>` | `material_property%dispersivity(1)` | `material.F90:386-388` |
| `TRANSVERSE_DISPERSIVITY_H <real>` | `material_property%dispersivity(2)` | `material.F90:389-391` |
| `TRANSVERSE_DISPERSIVITY_V <real>` | `material_property%dispersivity(3)` | `material.F90:392-394` |

The index meanings are confirmed by the named parameters in the kernel:
`LONGITUDINAL = 1`, `TRANSVERSE_HORIZONTAL = 2`, `TRANSVERSE_VERTICAL = 3`
(`src/pflotran/transport.F90:96-98`, repeated at `src/pflotran/transport.F90:296-298`).

**No unit conversion is applied.** Unlike `ROCK_DENSITY` or `SPECIFIC_HEAT`, which call
`InputReadAndConvertUnits` (`src/pflotran/material.F90:376-385`), the three dispersivity
readers are bare `InputReadDouble` calls — **the value is taken as metres, with no `UNITS`
support**.

**Default is zero.** `material_property%dispersivity = 0.d0`
(`src/pflotran/material.F90:254`), so omitting the card gives purely diffusive spreading.

**Path into the kernel.** `RTUpdateTransportCoefs` passes the *material property's* dispersivity
array (indexed by the cell's material id) straight through:

```fortran
      call TDispersion(global_auxvars(ghosted_id_up), &
                      material_auxvars(ghosted_id_up), &
                      local_Darcy_velocities_up, &
                     patch%material_property_array(patch%imat(ghosted_id_up))% &
                        ptr%dispersivity, &
```
(`src/pflotran/reactive_transport.F90:1294-1309`; boundary equivalent at
`src/pflotran/reactive_transport.F90:1339-1350`). So dispersivity is **per material, not per
phase and not per species**.

**How the transverse branch is armed.** `RTSetup` walks the material-property list once and sets
`calculate_transverse_dispersion = PETSC_TRUE` if *any* material has
`maxval(dispersivity(2:3)) > 0`:

```fortran
    if (maxval(cur_material_property%dispersivity(2:3)) > 0.d0) then
      rt_parameter%calculate_transverse_dispersion = PETSC_TRUE
      exit
    endif
```
(`src/pflotran/reactive_transport.F90:174-184`). This is global — one material with a
transverse dispersivity switches the *entire* domain onto the tensor branch and onto the
cell-centered velocity reconstruction (`src/pflotran/reactive_transport.F90:1237-1260`), which
costs three global-to-local Vec exchanges per phase per time step.

**Motivating-case note.** A deck with only `LONGITUDINAL_DISPERSIVITY` set stays on branch (a):
$D^{\text{mech}} = \alpha_L |q|$, no cell-centered velocity reconstruction, no tensor.

---

## 5. Molecular diffusion coefficient input

Three input surfaces, applied in this order inside `RTSetup`:

**(1) Per-phase, from `FLUID_PROPERTY`.** `DIFFUSION_COEFFICIENT` (alias
`LIQUID_DIFFUSION_COEFFICIENT`) is read at `src/pflotran/fluid.F90:109-115` with unit conversion
to `m^2/sec`; `DIFFUSION_ACTIVATION_ENERGY` at `src/pflotran/fluid.F90:123-130` converted to
`J/mol`. The `PHASE` card must be `LIQUID` or `GAS`
(`src/pflotran/fluid.F90:106-108, 143-146`), mapped to `phase_id` at
`src/pflotran/realization_subsurface.F90:1010-1017`. `RTSetup` then copies each fluid
property's coefficient into **all** diffusion-coefficient slots of its phase:

```fortran
    iphase = cur_fluid_property%phase_id
    if (iphase <= option%transport%nphase) then
      rt_parameter%diffusion_coefficient(:,iphase) = &
        cur_fluid_property%diffusion_coefficient
```
(`src/pflotran/reactive_transport.F90:337-350`).

> **Gotcha.** `FLUID_PROPERTY`'s `GAS_DIFFUSION_COEFFICIENT` card
> (`src/pflotran/fluid.F90:131-134`, default `2.13d-5`, `src/pflotran/fluid.F90:59`) is **not**
> consumed by the GIRT/OSRT path. Grepping the tree, `%gas_diffusion_coefficient` is read only
> by `sco2.F90:215` and `mphase_aux.F90:450`. To set a gas-phase diffusion coefficient for
> reactive transport you need a **second `FLUID_PROPERTY` block with `PHASE GAS` and
> `DIFFUSION_COEFFICIENT`**, or the per-species route below.

**(2) Per-species, from `CHEMISTRY`.** `AQUEOUS_DIFFUSION_COEFFICIENTS` and
`GAS_DIFFUSION_COEFFICIENTS` are parsed as name/value lists
(`src/pflotran/reaction.F90:236-263`) and applied per primary species
(`src/pflotran/reactive_transport.F90:386-403` aqueous, `409-443` gas). Species not found in
the basis are fatal (`src/pflotran/reactive_transport.F90:380-385, 429-434`).

Declaring either list is what turns on **species-dependent diffusion**: `RTSetup` sizes
`ndiffcoef` accordingly —

```fortran
  temp_int = 1
  if (associated(reaction%aq_diffusion_coefficients) .or. &
      associated(reaction%gas_diffusion_coefficients)) then
    temp_int = reaction%naqcomp
  endif
```
(`src/pflotran/reactive_transport.F90:146-151`), and `ndiffcoef > 1` then triggers two
restrictions (`src/pflotran/reactive_transport.F90:445-461`): active gases must map one-to-one
to primary species, and aqueous complexation (`neqcplx > 0`) is rejected because "fluxes are
currently implemented based on the total aqueous component concentration and the diffusion of
secondary complexes is lumped." It is also fatal under OSRT
(`src/pflotran/pmc_subsurface_osrt.F90:299-303`).

**(3) The struct default.** `RTAuxCreate` initializes
`diffusion_coefficient = 1.d-9` m²/s for every coefficient and phase, and
`diffusion_activation_energy = UNINITIALIZED_DOUBLE`
(`src/pflotran/reactive_transport_aux.F90:180-183`). `fluid_property%diffusion_coefficient`
carries the same `1.d-9` default (`src/pflotran/fluid.F90:58`).

`NERNST_PLANCK` overrides all of this: it allocates per-species coefficients at `1.d-9` and
sets `diffusion_coefficient = 1.d-40` with the comment "Set diffusion_coefficient to 0 to skip
TDispersion and TDispersionBC diffusion influence"
(`src/pflotran/reactive_transport.F90:353-360`).

---

## 6. Advection — upwinding and the assembled face coefficient

`TFluxCoef` (`src/pflotran/transport.F90:520-600`) combines the stored dispersion coefficient
with the Darcy flux $q$ using **pure single-point upwinding**:

```fortran
      if (q > 0.d0) then
        coef_up(:) =  tran_coefs_over_dist(1,iphase)+q
        coef_dn(:) = -tran_coefs_over_dist(1,iphase)
      else
        coef_up(:) =  tran_coefs_over_dist(1,iphase)
        coef_dn(:) = -tran_coefs_over_dist(1,iphase)+q
      endif
```
(`src/pflotran/transport.F90:584-592`; the `ndiffcoef > 1` branch at
`src/pflotran/transport.F90:576-583` is identical but per-species). Then

$$
T_{up} = \mathrm{coef}_{up}\cdot A \cdot 1000,\qquad
T_{dn} = \mathrm{coef}_{dn}\cdot A \cdot 1000
$$

converting m³ → L (`src/pflotran/transport.F90:594-597`), so $T$ has units of L water/sec.

> **Dead argument.** `fraction_upwind` is declared (`src/pflotran/transport.F90:545`) and passed
> by every caller with values `dist(-1,iconn)` (interior,
> `src/pflotran/reactive_transport.F90:2291`) or `0.5d0` (boundary, commented "fraction upwind
> (0.d0 upwind, 0.5 central)", `src/pflotran/reactive_transport.F90:1724`) — but it is **never
> referenced in the body**. Upwinding is unconditional at this commit. Central weighting is not
> reachable through this path.

**Dry-cell early return.** `TFluxCoef` returns zeroed coefficients if the downstream liquid
saturation is below `rt_min_saturation`, or (when `check_upwind_saturation` is true) if the
upstream one is (`src/pflotran/transport.F90:557-569`). Interior connections pass
`PETSC_TRUE`; boundaries pass `PETSC_FALSE` via `TFluxCoefBC`
(`src/pflotran/transport.F90:637-641`) with the comment that a zero aqueous saturation upwind
at a boundary "does not matter" (`src/pflotran/transport.F90:564-565`).

**Residual assembly.** `TFlux` (`src/pflotran/transport.F90:403-451`) forms

$$
F_\alpha = T_{up,\alpha}\,T^{\text{tot}}_{up,\alpha} + T_{dn,\alpha}\,T^{\text{tot}}_{dn,\alpha}
$$

for the liquid phase (`src/pflotran/transport.F90:438-441`) and **adds the gas phase when
`ngas > 0`** (`src/pflotran/transport.F90:443-449`). Units are mol/s
(`src/pflotran/transport.F90:436-437`). The derivative counterpart `TFluxDerivative`
(`src/pflotran/transport.F90:455-516`) uses `rt_auxvar%aqueous%dtotal(:,:,iphase)` when
available, falling back to a diagonal $\rho/1000$ form
(`src/pflotran/transport.F90:494-514`).

### TVD / explicit advection (a separate mode)

`CHEMISTRY` → `EXPLICIT_ADVECTION [UPWIND|MINMOD|MC|SUPERBEE|VANLEER]`
(`src/pflotran/reaction.F90:841-866`) switches `option%itranmode` to `EXPLICIT_ADVECTION` and
selects a flux limiter. The limiter functions are `TFluxLimitUpwind`, `TFluxLimitMinmod`,
`TFluxLimitMC`, `TFluxLimitSuperBee`, `TFluxLimitVanLeer`
(`src/pflotran/transport.F90:841-946`) with integer ids
`TVD_LIMITER_UPWIND=1 … TVD_LIMITER_VAN_LEER=5` (`src/pflotran/transport.F90:42-46`).
`RTExplicitAdvection` (`src/pflotran/reactive_transport.F90:4211`) rejects three
configurations outright (`src/pflotran/reactive_transport.F90:4367-4381`): `nphase > 1`,
`ncomp /= naqcomp` (i.e. any non-aqueous species), and `compute_mass_balance_new`.

---

## 7. Gas-phase transport (moved)

See: [`gas_phase_transport.md`](gas_phase_transport.md) — `ACTIVE_GAS_SPECIES`
vs `PASSIVE_GAS_SPECIES`, what `GAS_TRANSPORT_IS_UNVETTED` gates, and the eight concrete gaps in
the source that make active gas transport "unvetted" at this commit.

---

## 8. Calibration knobs on this page

| Keyword | Block | Source line | Units | Default | Controls |
|---|---|---|---|---|---|
| `LONGITUDINAL_DISPERSIVITY` | `MATERIAL_PROPERTY` | `material.F90:386-388` | m (no unit conversion) | `0.d0` (`material.F90:254`) | $\alpha_L$ in $D^{\text{mech}} = \alpha_L\lvert q\rvert$ |
| `TRANSVERSE_DISPERSIVITY_H` | `MATERIAL_PROPERTY` | `material.F90:389-391` | m (no unit conversion) | `0.d0` | $\alpha_{TH}$; **any nonzero value globally arms the tensor branch** (`reactive_transport.F90:174-184`) |
| `TRANSVERSE_DISPERSIVITY_V` | `MATERIAL_PROPERTY` | `material.F90:392-394` | m (no unit conversion) | `0.d0` | $\alpha_{TV}$; same global arming |
| `TORTUOSITY` | `MATERIAL_PROPERTY` | `material.F90:473-478` | – | `1.d0` (`material.F90:209`) | $\tau$ multiplier on $D^m$; must be 1 if Millington-Quirk is on |
| `ANISOTROPIC_TORTUOSITY` / `TORTUOSITY_X/_Y/_Z` | `MATERIAL_PROPERTY` | `material.F90:479-508` | – | off | direction-projected $\tau$ (`material_aux.F90:728-751`) |
| `TORTUOSITY_FUNCTION_OF_POROSITY <pwr>` | `MATERIAL_PROPERTY` | `material.F90:518-523` | – | off | $\tau = \phi^{\text{pwr}}$ (`material.F90:1032-1033`) |
| `USE_MILLINGTON_QUIRK_TORTUOSITY` | `SUBSURFACE_TRANSPORT,OPTIONS` | `pm_rt.F90:237-238` | – | off | $D^m \leftarrow S^{7/3}\phi^{1/3}D^m$ (`transport.F90:113-114, 157-166`) |
| `DIFFUSION_COEFFICIENT` / `LIQUID_DIFFUSION_COEFFICIENT` | `FLUID_PROPERTY` | `fluid.F90:109-115` | m²/s (converted) | `1.d-9` (`fluid.F90:58`, `reactive_transport_aux.F90:182`) | $D^m$ for the block's `PHASE` |
| `DIFFUSION_ACTIVATION_ENERGY` | `FLUID_PROPERTY` | `fluid.F90:123-130` | J/mol (converted) | uninitialized | Arrhenius exponent; **required** if `TRANSPORT_TEMPERATURE_DEPENDENCE ANISOTHERMAL` (`pm_rt.F90:437-452`) |
| `GAS_DIFFUSION_COEFFICIENT` | `FLUID_PROPERTY` | `fluid.F90:131-134` | m²/s (no conversion) | `2.13d-5` (`fluid.F90:59`) | **not used by GIRT/OSRT** — only `sco2.F90:215`, `mphase_aux.F90:450` |
| `AQUEOUS_DIFFUSION_COEFFICIENTS` | `CHEMISTRY` | `reaction.F90:236-260` | m²/s | absent | per-species liquid $D^m$; sets `ndiffcoef = naqcomp` |
| `GAS_DIFFUSION_COEFFICIENTS` | `CHEMISTRY` | `reaction.F90:236-262` | m²/s | absent | per-species gas $D^m$; requires an active gas |
| `ACTIVE_GAS_SPECIES` | `CHEMISTRY` | `reaction.F90:264-280` | – | absent | raises `nphase` to 2 (`reaction.F90:103-105`) — enables gas advection + diffusion + storage under GIRT |
| `GAS_TRANSPORT_IS_UNVETTED` | first card of `ACTIVE_GAS_SPECIES` | `reaction.F90:270-276` | – | **mandatory when `ACTIVE_GAS_SPECIES` is present** | nothing — pure acknowledgement token |
| `PASSIVE_GAS_SPECIES` | `CHEMISTRY` | `reaction.F90:283-285` | – | absent | diagnostic gases; no transport phase added |
| `MINIMUM_SATURATION` | `SUBSURFACE_TRANSPORT,OPTIONS` | `pm_rt.F90:225-227` | – | `1.d-40` (`reactive_transport_aux.F90:20`) | dry-cell cutoff in `TDispersion`, `TFluxCoef`, `TSrcSinkCoef`, `RTAccumulation` |
| `EXPLICIT_ADVECTION [limiter]` | `CHEMISTRY` | `reaction.F90:841-866` | – | off | TVD explicit advection; single-phase, aqueous-only |

---

## 9. Related pages

- [`girt_and_operator_splitting.md`](girt_and_operator_splitting.md) — mode dispatch, the two
  solve algorithms, the full `OPTIONS` card list.
- [`transport_boundary_conditions.md`](transport_boundary_conditions.md) — BC semantics and how
  Darcy velocities arrive.
- [`gas_phase_transport.md`](gas_phase_transport.md) — the second mobile phase and
  `GAS_TRANSPORT_IS_UNVETTED`.
