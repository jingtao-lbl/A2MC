**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** `MODE RICHARDS`, `MODE TH`, `MODE MPHASE` (and the `_TS` variants) — equations, primary variables, options, and how they differ from GENERAL
**Last verified:** 2026-07-31

---

## 1. RICHARDS

Files: `src/pflotran/richards.F90` (driver, 3361 lines), `src/pflotran/richards_aux.F90` (auxvars, 512 lines), `src/pflotran/richards_common.F90` (accumulation/flux/BC, 825 lines), `src/pflotran/pm_richards.F90` (process model, 993 lines).

Sizing (`src/pflotran/factory_subsurface.F90:211-216`): `nphase = 1`, `nflowdof = 1`, `nflowspec = 1`, and **`option%flow%isothermal = PETSC_TRUE` is forced** (`:216`).

### Primary variable

One dof: **liquid pressure** [Pa], `RICHARDS_PRESSURE_DOF = 1` (`richards_aux.F90:24`). A second index `RICHARDS_CONDUCTANCE_DOF = 2` (`richards_aux.F90:25`) is not a solution dof; it is the slot in the boundary auxvar array where a conductance value is stored.

There is **no state variable and no state switching** — that machinery is specific to GENERAL/HYDRATE/SCO2. Saturation is a pure function of pressure through the characteristic curve.

`RichardsAuxVarCompute` (`richards_aux.F90:189-373`):

```
global_auxvar%pres  = x(1)                                   (richards_aux.F90:238)
global_auxvar%temp  = option%flow%reference_temperature      (:239)
auxvar%pc = min(reference_pressure - pres, sat_func%pcmax)   (:250-251)
pw = option%flow%reference_pressure                          (:254)
```

Two consequences a calibration agent must know:

1. **Temperature is not solved** — it is pinned to `option%flow%reference_temperature`, default `25.d0` °C (`src/pflotran/option_flow.F90:144`), settable by the `SUBSURFACE`-level `REFERENCE_TEMPERATURE` card (`factory_subsurface_read.F90:1407-1410`; note that card reads a bare double with **no unit conversion**, unlike `REFERENCE_PRESSURE`, so the value is taken as °C). All EOS calls use that value.
2. **Capillary pressure is measured from `REFERENCE_PRESSURE`, not from a gas-phase pressure.** $P_c = P_{ref} - P_l$, truncated at the saturation function's `pcmax`. The in-source comment (`richards_aux.F90:245-249`) explains the truncation exists because a very negative $P_l$ otherwise blows up the EOS. `REFERENCE_PRESSURE` therefore directly shifts the water-retention curve and is a first-class calibration knob for RICHARDS.

If `ds_dp < 1.d-40` the cell is declared saturated (`richards_aux.F90:292-295`), $k_r$ is not evaluated, and the saturated branch is taken.

### Governing equation

Accumulation, kmol/s (`richards_common.F90:112-142`):

$$R = \frac{s_l\,\rho_l\,\phi\,V}{\Delta t}$$

using `material_auxvar%porosity` (not the effective porosity used by GENERAL) (`richards_common.F90:139-140`).

Internal flux (`richards_common.F90:339-418`):

$$\Delta\Phi = P^{up} - P^{dn} + \bar\rho\,C_{kg}\,(\mathbf g\!\cdot\!\hat{\mathbf d})\,d,\qquad
v = D_q\,\left(\tfrac{k_r}{\nu}\right)^{up}\Delta\Phi,\qquad F = v\,A\,\bar\rho$$

- `kvr` is $k_r/\nu$ where $\nu$ is **kinematic** viscosity for RICHARDS (variable name `kvr`, used at `richards_common.F90:403`). This differs from GENERAL, whose `mobility` divides by dynamic viscosity.
- $C_{kg}$ is `richards_density_kmol_to_kg`, defaulting to `FMWH2O` (`richards_aux.F90:19`) so that the kmol/m³ density becomes kg/m³ in the gravity term. The `USE_MASS_DENSITY` option sets it to `1.d0` (`pm_richards.F90:163`). A guard at `richards_aux.F90:354-355` notes only those two values are legal.
- Upwinding is fully upstream on the sign of $\Delta\Phi$ (`richards_common.F90:398-402`); `upweight` for the density average is set to 0 or 1 when either cell is essentially dry (`richards_common.F90:383-388`).
- The flux is skipped entirely unless `ukvr > floweps` (`richards_common.F90:404`), `floweps = 1.d-24` (`richards_common.F90:17`).

### Boundary conditions

`RichardsBCFlux` (`richards_common.F90:679-823`) handles a narrower set than GENERAL:

| Type group | Line | Behavior |
|---|---|---|
| `DIRICHLET_BC`, `DIRICHLET_SEEPAGE_BC`, `DIRICHLET_CONDUCTANCE_BC`, and the hydrostatic/heterogeneous variants | `richards_common.F90:~730` | Two-point Darcy against boundary pressure; conductance types replace $D_q = k^{dn}/d$ with `auxvars(RICHARDS_CONDUCTANCE_DOF)` (`:742-748`) |
| `NEUMANN_BC` | `:791` | Darcy velocity read directly from `auxvars(RICHARDS_PRESSURE_DOF)` [m/s], gated by `floweps` (`:792-793`) |
| `UNIT_GRADIENT_BC` | `:803` | $\Delta\Phi = (\mathbf g\!\cdot\!\hat{\mathbf d})\,\rho^{dn} C_{kg}$ — gravity-driven free drainage, boundary auxvar unused (`:805-812`) |

**The RICHARDS seepage test is different from GENERAL's.** It is (`richards_common.F90:773-778`):

```fortran
if (dphi > 0.d0 .and. &
    global_auxvar_up%pres(1) - option%flow%reference_pressure < eps) then
  dphi = 0.d0
endif
```

i.e. inflow is clamped when the **boundary pressure is at or below `REFERENCE_PRESSURE`**. GENERAL instead tests the boundary ghost cell's capillary pressure and additionally swaps the driving pressure to the gas phase (see `boundary_conditions.md` §3). Both express "no inflow through an unsaturated face", but the trigger variable differs, so a deck ported between modes will not clamp at the same instants.

The same clamp is shared by `HYDROSTATIC_SEEPAGE_BC`, `HYDROSTATIC_CONDUCTANCE_BC`, `DIRICHLET_CONDUCTANCE_BC`, and the three `HET_*` seepage/conductance types (`richards_common.F90:767-771`) — note that in RICHARDS the **conductance** types also clamp, which is worth knowing if you meant a pure conductance boundary.

### `MODE RICHARDS` `OPTIONS`

`PMRichardsReadSimOptionsBlock` (`pm_richards.F90:109-170`). Beyond the shared cards (see `mode_selection.md` §4), only three:

| Keyword | Line | Arg | Effect |
|---|---|---|---|
| `INLINE_SURFACE_REGION` | `pm_richards.F90:155` | region name | `option%flow%inline_surface_flow = PETSC_TRUE`, names the surface region |
| `INLINE_SURFACE_MANNINGS_COEFF` | `:159` | real | Manning's coefficient for inline surface flow |
| `USE_MASS_DENSITY` | `:162` | — | `richards_density_kmol_to_kg = 1.d0` |

Anything else aborts (`pm_richards.F90:164-165`).

`RICHARDS_TS` (`factory_subsurface.F90:253-258`) has identical dimensioning; it swaps PFLOTRAN's own time loop for PETSc's `TS` object (external PETSc framework).

## 2. TH

Files: `src/pflotran/th.F90` (5624 lines: auxvar update, accumulation, flux, BC flux, Jacobian), `src/pflotran/th_aux.F90` (1172 lines), `src/pflotran/pm_th.F90`.

Sizing (`factory_subsurface.F90:246-252`): `nphase = 1`, `nflowdof = 2`, `nflowspec = 1`, `isothermal = PETSC_FALSE`, and `option%flow%store_fluxes = PETSC_TRUE` (`:252`).

### Primary variables

`TH_PRESSURE_DOF = 1`, `TH_TEMPERATURE_DOF = 2` (`th_aux.F90:19-20`); `TH_CONDUCTANCE_DOF = 3` is again a boundary-auxvar slot, not a solution dof (`:21`). Assigned in `THAuxVarComputeNoFreezing`:

```
global_auxvar%pres = x(1)      (th_aux.F90:407)
global_auxvar%temp = x(2)      (:408)
auxvar%pc = min(reference_pressure - pres, pcmax)   (:414-415)
```

So TH is RICHARDS plus an energy equation: **still a single (liquid) phase, still $P_c$ referenced to `REFERENCE_PRESSURE`.** TH is *not* a two-phase mode; if you need gas as a mobile phase, you need GENERAL.

### Governing equations

Water mass and energy accumulation (`th.F90:1387-1456`, annotated in-source as TechNotes TH-mode Eqs. 8 and 9):

$$R_1 = \frac{s_l\,\rho_l\,\phi V}{\Delta t}\ \text{[kmol/s]},\qquad
R_2 = \frac{f_{prim}}{\Delta t}\Big[s_l\rho_l u\,\phi V + (1-\phi)V\,\rho c_{pr}\,T\Big]\ \text{[MJ/s]}$$

(`th.F90:1424-1454`). With `FREEZING`, ice and gas contributions are added to both (`th.F90:1439-1450`).

Flux (`THFlux`, `th.F90:2124-…`): same Darcy form as RICHARDS but the gravity term uses `den*avgmw` per cell (`th.F90:2235-2237`), and the advected enthalpy `uh` is upwinded alongside `kvr` (`th.F90:2245-2251`). Two TH-specific wrinkles:

- `InterfaceApprox` post-processes the upwinded `ukvr` according to `option%flow%rel_perm_aveg` (`th.F90:2253-2254`) — TH supports relative-permeability averaging schemes that RICHARDS and GENERAL do not. The deck card is the `SUBSURFACE`-level `RELATIVE_PERMEABILITY_AVERAGE` with values `UPWIND` (default, `option_flow.F90:167`), `HARMONIC`, or `DYNAMIC_HARMONIC` (`factory_subsurface_read.F90:2474-2488`).
- `option%flow%only_energy_eq` zeroes the Darcy velocity so the mass equation contributes nothing (`th.F90:2260-2262`).
- With `ICE_MODEL DALL_AMICO`, the driving potential uses `ice%pres_fh2o` instead of the liquid pressure (`th.F90:2239-2243`).

Under `FREEZING`, TH adds a vapor-diffusion flux with its own hardcoded reference diffusivity `2.13D-5` m²/s, reference pressure `1.01325d5` Pa, and reference temperature `25 °C`, plus a $(T/T_{ref})^{1.8}$ scaling analogous to GENERAL's (`th.F90:2283-2290`). The in-source comment at `th.F90:2283` flags the diffusivity as hardcoded: *"Reference diffusivity, need to read from input file"* — **it is not deck-settable**. The same hardcoded value recurs at `th.F90:1775`, `:2831`, and `:3325`.

### Boundary conditions

`THBCFlux` (`th.F90:3025-…`) applies types separately to the two dofs:

- Pressure dof: `DIRICHLET_BC` / `DIRICHLET_SEEPAGE_BC` / `DIRICHLET_CONDUCTANCE_BC` and hydrostatic variants; `HET_SURF_HYDROSTATIC_SEEPAGE_BC`; `NEUMANN_BC`; `ZERO_GRADIENT_BC`. Seepage clamping mirrors RICHARDS.
- Temperature dof: `DIRICHLET_BC` / `HET_DIRICHLET_BC`, `NEUMANN_BC`, `ZERO_GRADIENT_BC`.

Note TH accepts `ZERO_GRADIENT` (RICHARDS does not in `RichardsBCFlux`, and GENERAL does not accept it at all — see `boundary_conditions.md` §1).

### `MODE TH` `OPTIONS`

`PMTHReadSimOptionsBlock` (`pm_th.F90:112-192`). Beyond the shared cards:

| Keyword | Line | Arg | Effect |
|---|---|---|---|
| `FREEZING` | `pm_th.F90:158` | — | `option%flow%th_freezing = PETSC_TRUE`. **Silent side effects:** it overrides the water EOS, calling `EOSWaterSetDensity('PAINTER')` and `EOSWaterSetEnthalpy('PAINTER')` (`pm_th.F90:163-164`), and prints *"TH: using FREEZING submode!"*. If you also set `EOS WATER DENSITY …` in the deck, ordering matters. |
| `ICE_MODEL` | `:165` | one of `PAINTER_EXPLICIT`, `PAINTER_KARRA_IMPLICIT`, `PAINTER_KARRA_EXPLICIT`, `PAINTER_KARRA_EXPLICIT_NOCRYO`, `DALL_AMICO` | Sets `th_ice_model` (`pm_th.F90:169-178`); anything else aborts with the list printed (`:180-184`) |

Anything else aborts (`pm_th.F90:186-187`).

`TH_TS` (`factory_subsurface.F90:259-265`) is TH under PETSc `TS`.

## 3. MPHASE

Files: `src/pflotran/mphase.F90` (4064 lines), `src/pflotran/mphase_aux.F90` (709 lines), `src/pflotran/mphase_pckr_mod.F90`, `src/pflotran/pm_mphase.F90`.

Sizing (`factory_subsurface.F90:201-210`): `nphase = 2`, `nflowdof = 3`, `nflowspec = 2`, `isothermal = PETSC_FALSE`, `water_id = 1`, `air_id = 2`. It also forces the CO2 property table mode, `co2_sw_itable = 2` — *"read CO2DATA0.dat"* (`factory_subsurface.F90:206`).

MPHASE forces `option%flow%numerical_derivatives = PETSC_TRUE` from inside `mphase.F90:254`, i.e. at setup rather than at deck-parse time (contrast GENERAL, which does it during `MODE` parsing — `mode_selection.md` §2).

### `MODE MPHASE` `OPTIONS`

`PMMphaseReadSimOptionsBlock` (`pm_mphase.F90:70-121`) has **no mode-specific keywords at all** — its `select case` contains only `case default` → `InputKeywordUnrecognized` (`pm_mphase.F90:115-117`). The only options MPHASE accepts are the shared base and subsurface-flow ones listed in `mode_selection.md` §4.

MPHASE uses the **generic** flow-condition reader (`factory_subsurface_read.F90:1211-1212`), and per the mode guard at `condition.F90:1583-1590` it **cannot use `DIRICHLET_SEEPAGE` or `DIRICHLET_CONDUCTANCE`** on a pressure condition.

Detailed MPHASE equations are not documented here; the mode is CO2-sequestration-oriented and is not the target of the basalt-column case.

## 4. Side-by-side: what to expect when moving a deck between modes

| | RICHARDS | TH | GENERAL |
|---|---|---|---|
| Phases solved | liquid only | liquid only | liquid + gas |
| dof | 1 | 2 | 3 (4 with `SOLUTE`) |
| Primary variables | $P_l$ | $P_l$, $T$ | state-dependent (see `general_mode.md` §3) |
| Temperature | fixed at `reference_temperature` (25 °C) | solved | solved, or frozen by `ISOTHERMAL` |
| $P_c$ reference | `REFERENCE_PRESSURE` − $P_l$ | `REFERENCE_PRESSURE` − $P_l$ | $P_g$ − $P_l$ (explicit gas pressure) |
| Phase appearance | n/a | n/a | `GeneralAuxVarUpdateState` |
| Mobility definition | $k_r/\nu$ (kinematic) | $k_r/\nu$ | $k_r/\mu$ (dynamic) |
| Porosity used in accumulation | `material_auxvar%porosity` | `material_auxvar%porosity` | `gen_auxvar%effective_porosity` |
| Condition reader | generic | generic | `FlowConditionGeneralRead` |
| Seepage clamp trigger | $P^{bnd} \le P_{ref}$ | same as RICHARDS | $P_c^{bnd} > 0$ **and** driving pressure switched to $P_g$ |
| `ZERO_GRADIENT` BC | not in `RichardsBCFlux` | yes | no |
| `UNIT_GRADIENT` BC | yes | — | no |
| Default Jacobian | analytical (framework default) | analytical | **numerical** (forced at `MODE` parse) |

**Porting caution.** Moving from RICHARDS to GENERAL is not a superset operation: `REFERENCE_PRESSURE` stops controlling $P_c$, a gas pressure must be supplied in every flow condition, a `TEMPERATURE` sub-condition becomes mandatory, and the condition-type vocabulary changes (`boundary_conditions.md` §1). Conversely, moving GENERAL → RICHARDS silently discards the gas phase and freezes temperature at 25 °C unless `REFERENCE_TEMPERATURE` is set.

## 5. Calibration knobs (RICHARDS / TH)

| Keyword | Block | Source line | Units | Default | Controls |
|---|---|---|---|---|---|
| `REFERENCE_PRESSURE` | `SUBSURFACE` | `factory_subsurface_read.F90:1369` | Pa | `101325` (`option_flow.F90:143`) | Datum for $P_c = P_{ref}-P_l$ in both modes; also the seepage clamp threshold |
| `REFERENCE_LIQUID_DENSITY` | `SUBSURFACE` | `factory_subsurface_read.F90:1377` | kg/m³ | — | Reference liquid density |
| `REFERENCE_GAS_DENSITY` | `SUBSURFACE` | `factory_subsurface_read.F90:1387` | kg/m³ | — | Reference gas density |
| `MINIMUM_HYDROSTATIC_PRESSURE` | `SUBSURFACE` | `factory_subsurface_read.F90:1397` | Pa | — | Floor on hydrostatic BC reconstruction |
| `REFERENCE_TEMPERATURE` | `SUBSURFACE` | `factory_subsurface_read.F90:1407` | °C (no unit conversion applied) | `25.d0` (`option_flow.F90:144`) | Fixed temperature for RICHARDS EOS calls |
| `RELATIVE_PERMEABILITY_AVERAGE` | `SUBSURFACE` | `factory_subsurface_read.F90:2474` | — | `UPWIND` (`option_flow.F90:167`) | Interface $k_r$ scheme (TH) |
| `USE_MASS_DENSITY` | `SUBSURFACE_FLOW/OPTIONS` (RICHARDS) | `pm_richards.F90:162` | — | off (uses `FMWH2O`) | Switches `richards_density_kmol_to_kg` to 1 |
| `INLINE_SURFACE_MANNINGS_COEFF` | `SUBSURFACE_FLOW/OPTIONS` (RICHARDS) | `pm_richards.F90:159` | not stated in source | — | Inline surface flow resistance |
| `ICE_MODEL` | `SUBSURFACE_FLOW/OPTIONS` (TH) | `pm_th.F90:165` | — | unset | Freezing-curve formulation |
| `FREEZING` | `SUBSURFACE_FLOW/OPTIONS` (TH) | `pm_th.F90:158` | — | off | Enables ice; overrides water EOS to `PAINTER` |
| `GRAVITY x y z` | `GRID` | `discretization.F90:472` | m/s² | `(0,0,-9.8068)` | Body force |
| `PRESSURE_DAMPENING_FACTOR` | `NUMERICAL_METHODS FLOW/NEWTON_SOLVER` | `pm_subsurface_flow.F90:286` | – | — | Newton damping on pressure |
| `SATURATION_CHANGE_LIMIT` | same | `:290` | – | — | Per-iteration saturation clamp |
| `PRESSURE_CHANGE_LIMIT` | same | `:294` | Pa | — | Per-iteration pressure clamp |
| `TEMPERATURE_CHANGE_LIMIT` | same | `:298` | °C | — | Per-iteration temperature clamp (TH) |
| `ANALYTICAL_JACOBIAN` / `NUMERICAL_JACOBIAN` | same | `:305` / `:302` | — | analytical for RICHARDS/TH | Jacobian mode |

`reference_temperature` (default `25.d0` °C, `option_flow.F90:144`) governs every RICHARDS EOS call. Unlike `REFERENCE_PRESSURE` (`factory_subsurface_read.F90:1369-1374`), the `REFERENCE_TEMPERATURE` card does **not** call `InputReadAndConvertUnits` (`factory_subsurface_read.F90:1407-1410`), so its value is consumed as-is in °C with no unit string accepted.

## 6. Not verifiable from static reading

- Whether a given seepage face actually clamps during a run (depends on the evolving pressure field).
- Numerical behavior of `InterfaceApprox` averaging vs. pure upwinding in TH — the card is traced (`RELATIVE_PERMEABILITY_AVERAGE`), but which choice performs better for a given problem is a runtime question.
- MPHASE's residual/Jacobian details were not read line-by-line; only its dimensioning, option list (empty), and derivative default are documented above.
