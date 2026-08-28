**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** Flow boundary and source/sink condition types honored by the flow modes — parsing, semantics, and what `DIRICHLET_SEEPAGE` actually does
**Last verified:** 2026-07-31

---

## 1. Two different BC vocabularies

`FLOW_CONDITION` blocks are dispatched by mode (`src/pflotran/factory_subsurface_read.F90:1204-1213`). GENERAL and WIPP_FLOW use `FlowConditionGeneralRead`; RICHARDS, TH, MPHASE, ZFLOW, PNF and the `_TS` variants use `FlowConditionRead`. **The two readers accept different type lists.** A type valid in RICHARDS may not parse in GENERAL and vice versa.

| Deck string under `TYPE` | `itype` constant | GENERAL reader line | Generic reader line |
|---|---|---|---|
| `DIRICHLET` | `DIRICHLET_BC` | `condition.F90:2143` | `condition.F90:1256` |
| `NEUMANN` | `NEUMANN_BC` | `:2145` | `:1258` |
| `HYDROSTATIC` | `HYDROSTATIC_BC` | `:2147` | `:1313` |
| `CONDUCTANCE` | `HYDROSTATIC_CONDUCTANCE_BC` | `:2149` | `:1315` |
| `SEEPAGE` | `HYDROSTATIC_SEEPAGE_BC` | `:2151` | `:1321` |
| `DIRICHLET_SEEPAGE` | `DIRICHLET_SEEPAGE_BC` | `:2153` | `:1323` |
| `DIRICHLET_CONDUCTANCE` | `DIRICHLET_CONDUCTANCE_BC` | — (not accepted) | `:1325` |
| `ZERO_GRADIENT` | `ZERO_GRADIENT_BC` | — | `:1317` |
| `UNIT_GRADIENT` | `UNIT_GRADIENT_BC` | — | `:1332` (pressure sub-condition only, `:1333-1337`) |
| `AT_SOLUBILITY` | `AT_SOLUBILITY_BC` | `:2155` | — |
| `MASS_RATE` | `MASS_RATE_SS` | `:2157` | `:1260` |
| `TOTAL_MASS_RATE` | `TOTAL_MASS_RATE_SS` | `:2160` | `:1263` |
| `VOLUMETRIC_RATE` | `VOLUMETRIC_RATE_SS` | `:2190` | `:1327` |
| `SCALED_MASS_RATE` | `SCALED_MASS_RATE_SS` | `:2163` | `:1272` |
| `SCALED_VOLUMETRIC_RATE` | `SCALED_VOLUMETRIC_RATE_SS` | `:2193` | `:1272` |
| `SCALED_ENERGY_RATE` | `SCALED_ENERGY_RATE_SS` | — | `:1272` |
| `PRESSURE_REGULATED_MASS_RATE` | `PRES_REG_MASS_RATE_SS` | — | `:1272` |
| `ENERGY_RATE` | `ENERGY_RATE_SS` | — | `:1266` |
| `EQUILIBRIUM` | `EQUILIBRIUM_SS` | — | `:1330` |
| `WELL` / `PRODUCTION_WELL` / `INJECTION_WELL` | `WELL_SS` | — | `:1319` |
| `HETEROGENEOUS_DIRICHLET` | `HET_DIRICHLET_BC` | `:2226` | `:1345` |
| `HETEROGENEOUS_VOLUMETRIC_RATE` | `HET_VOL_RATE_SS` | `:2220` | `:1339` |
| `HETEROGENEOUS_MASS_RATE` | `HET_MASS_RATE_SS` | `:2223` | `:1342` |
| `HETEROGENEOUS_ENERGY_RATE` | `HET_ENERGY_RATE_SS` | — | `:1269` |
| `HETEROGENEOUS_SEEPAGE` | `HET_HYDROSTATIC_SEEPAGE_BC` | — | `:1347` |
| `HETEROGENEOUS_CONDUCTANCE` | `HET_HYDROSTATIC_CONDUCTANCE_BC` | — | `:1349` |
| `HETEROGENEOUS_SURFACE_SEEPAGE` | `HET_SURF_HYDROSTATIC_SEEPAGE_BC` | `:2228` | `:1351` |
| `SPILLOVER` | `SPILLOVER_BC` | — | `:1353` |
| `SURFACE_DIRICHLET` | `SURFACE_DIRICHLET` | — | `:1355` |
| `SURFACE_ZERO_GRADHEIGHT` | `SURFACE_ZERO_GRADHEIGHT` | — | `:1357` |
| `SURFACE_SPILLOVER` | `SURFACE_SPILLOVER` | — | `:1359` |

Anything else aborts via `InputKeywordUnrecognized` (`condition.F90:2230-2232` for GENERAL, `:1361-1363` for the generic reader).

The three `SCALED_*` / `PRES_REG_*` types require a trailing sub-type word — one of `NEIGHBOR_PERM`, `VOLUME`, `PERM` — and abort if it is missing (`condition.F90:2166-2189` GENERAL, `:1290-1312` generic).

## 2. GENERAL sub-condition names (the dof each `TYPE` line applies to)

Under GENERAL, each line inside `TYPE` names a sub-condition first, then its type. Valid sub-condition names are the `case` labels in `FlowGeneralSubConditionPtr` (`condition.F90:446-561`):

`LIQUID_PRESSURE` (`:470`), `GAS_PRESSURE` (`:477`), `LIQUID_SATURATION` or `GAS_SATURATION` (`:484`, aliased to the same pointer), `PRECIPITATE_SATURATION` (`:491`), `TEMPERATURE` (`:498`), `RELATIVE_HUMIDITY` (`:505`), `MOLE_FRACTION` (`:512`), `SALT_MOLE_FRACTION` (`:519`), `LIQUID_FLUX` (`:526`), `GAS_FLUX` (`:533`), `ENERGY_FLUX` (`:540`), `RATE` (`:547`). Anything else aborts (`:554-556`).

`LIQUID_SATURATION` values are silently converted to gas saturation on read: `rarray = 1 - rarray` (`condition.F90:2332-2338`).

### Units enforced on the values (`condition.F90:2295-2325`)

| Sub-condition | Internal units | Line |
|---|---|---|
| `LIQUID_PRESSURE`, `GAS_PRESSURE` | `Pa` | `:2296-2297` |
| `LIQUID_SATURATION`, `GAS_SATURATION`, `MOLE_FRACTION`, `RELATIVE_HUMIDITY`, `SALT_MOLE_FRACTION`, `PRECIPITATE_SATURATION`, `AT_SOLUBILITY` | `unitless` | `:2298-2301` |
| `TEMPERATURE` | `C` | `:2302-2303` |
| `LIQUID_FLUX`, `GAS_FLUX` | `meter/sec` (Darcy velocity) | `:2319-2320` |
| `ENERGY_FLUX` | `MW/m^2` or `MJ/m^2-sec`, units **mandatory** (`input%force_units`) | `:2321-2325` |
| `RATE` | 3 (or 4 with salt) components: mass-or-volume rate ×2 (×3), then `MJ/sec\|MW`; units mandatory | `:2304-2318` |

`LIQUID_FLUX` and `GAS_FLUX` are **Darcy velocities in m/s**, not mass or volumetric rates. This is easy to get wrong.

### Required combinations

A GENERAL non-rate condition must supply (`condition.F90:2383-2401`):
1. a liquid **or** gas pressure,
2. a mole fraction, relative humidity, **or** gas/liquid saturation,
3. a temperature — **required even with `ISOTHERMAL`**.

The **state of the boundary/initial condition is inferred from which sub-conditions are present**, not declared (`condition.F90:2402-2458`):

| Sub-conditions present | Inferred `condition%iphase` | Line |
|---|---|---|
| gas pressure + gas saturation + liquid pressure + (mole fraction or RH) | `MULTI_STATE` | `:2408` |
| gas pressure + gas saturation | `TWO_PHASE_STATE` (or `LGP_STATE` with salt at solubility) | `:2409-2423` |
| liquid pressure + mole fraction | `LIQUID_STATE` (or `LP_STATE` with salt at solubility) | `:2435-2445` |
| gas pressure + (mole fraction or RH) | `GAS_STATE` (or `GP_STATE`) | `:2446-2458` |
| liquid pressure + precipitate saturation + mole fraction | `LP_STATE` | `:2425-2429` |
| any `RATE` | `ANY_STATE` | `:2373-2374` |
| `LIQUID_FLUX` + `GAS_FLUX` + (energy flux or temperature) | `ANY_STATE` | `:2375-2380` |

There is **no `STATE` card in `FlowConditionGeneralRead`.** The only `case('STATE')` in `condition.F90` is at `:3461`, inside `FlowConditionHydrateRead`. If you want a two-phase boundary in GENERAL, give it `GAS_PRESSURE` + `GAS_SATURATION` + `TEMPERATURE`.

### Auxvar packing

The values are packed into a flat per-connection array whose indices are set in `PatchUpdateCouplerGeneral` (`src/pflotran/patch.F90:1610-1634`): dof 1 holds gas/liquid pressure and liquid flux; dof 2 holds temperature and energy flux; dof 3 holds mole fraction, gas saturation, air pressure, gas flux, and gas water mole fraction; dof 4 (salt runs) holds salt mole fraction, precipitate saturation, and porosity. `GeneralBCFlux` reads them back through `auxvar_mapping(GENERAL_*_INDEX)`.

## 3. What each type does in `GeneralBCFlux`

`GeneralBCFlux` (`src/pflotran/general_common.F90:2489-3961`) treats the boundary as a ghost cell (`gen_auxvar_up`) adjacent to the interior cell (`gen_auxvar_dn`). The phase loop appears twice, once for liquid (`general_common.F90:2645-…`) and once for gas (`:3029-…`), with identical structure.

### `DIRICHLET_BC` and `HYDROSTATIC_BC`

Grouped with the seepage/conductance types in the same `case` (`general_common.F90:2653-2654`, `:3033-3034`). Standard two-point Darcy flux against the prescribed boundary state:

$$\Delta P = P^{bnd}_\alpha - P^{dn}_\alpha + \bar\rho^{kg}_\alpha\,(\mathbf g\!\cdot\!\hat{\mathbf d})\,d,\qquad
\frac{\bar k}{d}\big|_{bnd} = \frac{k^{dn}_\alpha}{d}$$

(`general_common.F90:2661-2703`). Note the one-sided permeability: only the interior cell's permeability is used, divided by the full face distance (`:2672`). The boundary density derivative is forced to zero (`:2699`), since the boundary state is fixed.

`HYDROSTATIC` differs from `DIRICHLET` only at **setup** time: the pressure profile is generated from a `DATUM` and a gradient by `hydrostatic.F90` rather than being read cell-by-cell. At flux time it is indistinguishable from `DIRICHLET` (`general_common.F90:2678`).

### `HYDROSTATIC_CONDUCTANCE_BC`

Replaces $\bar k/d$ with a user-supplied conductance read from the auxvar array (`general_common.F90:2663-2670`), indexed by `GENERAL_LIQUID_CONDUCTANCE_INDEX` / `GENERAL_GAS_CONDUCTANCE_INDEX`. The conductance value comes from the `CONDUCTANCE` card of the flow condition (`condition.F90:2276-2283`).

### `DIRICHLET_SEEPAGE_BC` — what it actually does

This is the type on the outflow face of the basalt column. The mechanics are in three steps.

**Step 1 — decide whether water can flow *in*.** For every type *except* plain `DIRICHLET` and `HYDROSTATIC` (`general_common.F90:2677-2684`):

```fortran
select case(bc_type)
  case(DIRICHLET_BC,HYDROSTATIC_BC)
  case default
     if (gen_auxvar_up%pres(option%capillary_pressure_id) > 0.d0) then
       water_cannot_flow_in = PETSC_TRUE
       boundary_pressure = gen_auxvar_up%pres(option%gas_phase)
     endif
end select
```

So the seepage test keys off the **boundary ghost cell's capillary pressure**. If the boundary state is unsaturated ($P_c > 0$), water is flagged as unable to enter, *and* the driving pressure is switched from the liquid pressure to the **gas** pressure of the boundary. That second part is easy to miss and it changes $\Delta P$ even before any clamping.

**Step 2 — clamp inflow.** For `DIRICHLET_SEEPAGE_BC` specifically (`general_common.F90:2726-2735`):

```fortran
if (bc_type == DIRICHLET_SEEPAGE_BC) then
  if (delta_pressure > 0.d0 .and. water_cannot_flow_in) then
    delta_pressure = 0.d0
    ...
  endif
endif
```

`delta_pressure > 0` means flow **into** the domain (boundary pressure exceeds interior pressure after the gravity term). When that happens on an unsaturated boundary, the driving force is zeroed — no flux. Outflow (`delta_pressure < 0`) is left untouched. That is the seepage face: **free outflow, no inflow when the face is not ponded.**

`HYDROSTATIC_SEEPAGE_BC` and `HYDROSTATIC_CONDUCTANCE_BC` apply the identical clamp in a separate block (`general_common.F90:2711-2724`). The difference from `DIRICHLET_SEEPAGE_BC` is only where the boundary pressure profile came from (hydrostatic reconstruction vs. a directly prescribed Dirichlet value).

**Step 3 — free-surface special case.** Independently of type, if the boundary ghost cell is in `GAS_STATE`, the liquid-phase driving pressure is replaced by the gas pressure (`general_common.F90:2685-2691`), with the in-source comment that this accommodates a free-surface boundary face and would be wrong for an interior connection.

**Analytical-derivative restriction.** If the clamp fires while `analytical_derivatives` is true, PFLOTRAN aborts with *"DIRCHLET_SEEPAGE_BC needs to be verified in GeneralBCFlux()"* (typo in source, `general_common.F90:2730-2732`). The sibling message for the hydrostatic variants is at `:2717-2719`. **Use the default numerical Jacobian on any deck with a seepage face in GENERAL mode.**

**Mode restriction does not apply here.** The guard at `condition.F90:1583-1590` that limits `DIRICHLET_SEEPAGE_BC` to RICHARDS/TH/ZFLOW lives in the *generic* reader, which GENERAL does not use. See §5.

### `NEUMANN_BC`

For the phase loop (`general_common.F90:2780-2816`), the Darcy machinery is bypassed entirely: all pressure-derived quantities are zeroed and the Darcy velocity is taken straight from the auxvar (`:2801-2802`):

```fortran
if (dabs(auxvars(idof)) > floweps) then
  v_darcy(iphase) = auxvars(idof)
```

with `idof = auxvar_mapping(GENERAL_LIQUID_FLUX_INDEX)` or `GENERAL_GAS_FLUX_INDEX` (`:2789-2794`). Density and enthalpy are taken from the boundary if the flux is into the domain, from the interior cell if out (`:2807-2815`). `xmol_bool = 0.d0` (`:2781`) suppresses the mole-fraction derivative contributions.

Note the `floweps` guard: a **prescribed flux smaller than `floweps` in magnitude is treated as exactly zero**, and `v_darcy` stays 0. `floweps` is a module-private parameter, `1.d-24` (`general_common.F90:32`).

For the energy equation (`general_common.F90:3924-3930`), `NEUMANN` means a prescribed heat flux in **MW/m²**, multiplied by area to give MJ/s:

```fortran
heat_flux = auxvars(auxvar_mapping(GENERAL_ENERGY_FLUX_INDEX)) * area
```

The energy equation accepts only `DIRICHLET_BC` (conductive, `:3905-3923`) and `NEUMANN_BC`; anything else aborts (`general_common.F90:3931-3934`).

**Diffusion still acts across a Neumann face.** The diffusion block runs when `sat_dn > eps .and. ibndtype(iphase) /= NEUMANN_BC`, *or* when the face is Neumann but a Dirichlet solute/mole-fraction sub-condition was supplied (`general_common.F90:3396-3397`). So a "zero-flux" Neumann boundary is not automatically a no-mass-transfer boundary if a mole fraction was also prescribed.

Any other `bc_type` reaching the phase loop aborts with *"Boundary condition type not recognized in GeneralBCFlux phase loop"* (`general_common.F90:2817-2820`).

## 4. Time-varying boundary values

Values for any sub-condition are read by `ConditionReadValues` (`condition.F90:4180-4316`), which branches on the first token (`condition.F90:4243-4307`):

| First token | Meaning | Line |
|---|---|---|
| a number | single constant value | `condition.F90:4303-4306` |
| `FILE <name>` | time series from an ASCII file, via `DatasetAsciiReadFile` | `:4244-4279` |
| `LIST` … `/` | inline time/value pairs, via `DatasetAsciiReadList` | `:4288-4291` |
| `DATASET <name>` | reference to a named `DATASET` block (HDF5 or gridded) | `:4280-4286` |
| `DBASE_VALUE` | parameter-database substitution | `:4292-4295` |

Anything else aborts (`:4297-4301`).

Time interpolation between entries is controlled by the condition-level `INTERPOLATION` card, `STEP` (default) or `LINEAR` (`condition.F90:2109-2120`; the default is set at `:2079`). `CYCLIC` makes the series repeat (`:2104-2106`). `SYNC_TIMESTEP_WITH_UPDATE` forces the time stepper to land exactly on each entry's time (`:2107-2108`).

A **time-varying flux boundary** therefore looks like:

```
FLOW_CONDITION infiltration
  TYPE
    LIQUID_FLUX NEUMANN
    GAS_FLUX NEUMANN
    TEMPERATURE DIRICHLET
  /
  INTERPOLATION LINEAR
  LIQUID_FLUX LIST
    TIME_UNITS d
    DATA_UNITS m/s
    0.d0   1.d-8
    30.d0  5.d-8
  /
  GAS_FLUX 0.d0 m/s
  TEMPERATURE 15.d0 C
END
```

(The `LIST` sub-keywords `TIME_UNITS` / `DATA_UNITS` are parsed by `DatasetAsciiReadList` in `dataset_ascii.F90`, outside this topic's scope; the units enforced on the data are the internal units in §2.)

`GRADIENT` blocks attach a spatial gradient (3-vector, `unitless/meter`) to any sub-condition (`condition.F90:2246-2275`), and `DATUM` sets the reference point for hydrostatic reconstruction (`condition.F90:2236-2245`).

## 5. Generic-reader (RICHARDS / TH / MPHASE / ZFLOW / PNF) sub-conditions

`FlowConditionRead` resolves sub-condition names against a fixed set of local pointers rather than a helper function (`condition.F90:1225-1250`):

| Deck name | Line | Target |
|---|---|---|
| `LIQUID_PRESSURE` | `:1226` | `pressure` |
| `RATE` | `:1228` | `rate` |
| `ENERGY_RATE` | `:1230` | `energy_rate` |
| `WELL` | `:1232` | `well` |
| `LIQUID_FLUX` | `:1234` | `flux` |
| `ENERGY_FLUX` | `:1236` | `energy_flux` |
| `LIQUID_SATURATION` | `:1238` | `saturation` |
| `TEMPERATURE` | `:1240` | `temperature` |
| `CONCENTRATION` | `:1242` | `concentration` |
| `ENTHALPY` | `:1244` | `enthalpy` |
| `PRESSURE`, `SATURATION`, `FLUX` | `:1246` | **deprecated**, redirected to the `LIQUID_` forms |

Unknown names abort (`:1248-1249`). `UNIT_GRADIENT` is restricted to the pressure sub-condition and errors otherwise (`condition.F90:1332-1338`).

### `DIRICHLET_SEEPAGE` is mode-restricted in the generic reader

`FlowConditionRead` enforces (`condition.F90:1571-1592`):

```fortran
select case(option%iflowmode)
  case(RICHARDS_MODE,TH_MODE,ZFLOW_MODE)          ! allowed
  case(PNF_MODE)                                   ! only DIRICHLET / NEUMANN
  case default
    if (pressure%itype == DIRICHLET_SEEPAGE_BC .or. &
        pressure%itype == DIRICHLET_CONDUCTANCE_BC) then
      ... 'only supported for RICHARDS, TH and ZFLOW.'
```

So among the generic-reader modes, `DIRICHLET_SEEPAGE` / `DIRICHLET_CONDUCTANCE` on a pressure condition work in **RICHARDS, TH, and ZFLOW only**; MPHASE and the other default-branch modes abort. `PNF_MODE` is narrower still — only `DIRICHLET_BC` and `NEUMANN_BC` (`:1576-1582`). **GENERAL is unaffected by this guard** because it goes through `FlowConditionGeneralRead`, which has no such check; `DIRICHLET_SEEPAGE` is accepted there (`condition.F90:2153`) and implemented in `GeneralBCFlux` (`general_common.F90:2726`).

A separate guard forbids a `RATE` sub-condition from carrying any BC-flavored type, including `DIRICHLET_SEEPAGE_BC` (`condition.F90:1599-1611`).

## 6. Cautions

- **`DIRICHLET_SEEPAGE` on a fully saturated boundary does nothing.** The clamp requires $P_c^{bnd} > 0$. If the boundary condition is specified so that the ghost cell is in `LIQUID_STATE` (where `pres(cpid)` is hardcoded to 0, `general_aux.F90:801`), `water_cannot_flow_in` never becomes true and the face behaves as a plain Dirichlet. Verify the boundary state your sub-condition combination implies (§2).
- The seepage clamp modifies `delta_pressure` **after** the gravity term is added (`general_common.F90:2701-2703` then `:2726`), so it is the gravity-corrected driving force that is tested, not the raw pressure difference.
- `HET_*` (heterogeneous) types read per-connection values from a dataset; GENERAL accepts only `HETEROGENEOUS_DIRICHLET`, `HETEROGENEOUS_VOLUMETRIC_RATE`, `HETEROGENEOUS_MASS_RATE`, and `HETEROGENEOUS_SURFACE_SEEPAGE` (`condition.F90:2220-2229`). `HETEROGENEOUS_SEEPAGE` and `HETEROGENEOUS_CONDUCTANCE` are **generic-reader only** and will not parse under `MODE GENERAL`.
- Nothing in the static source tells you what happens numerically when a seepage face oscillates between clamped and unclamped states across Newton iterations; that is a runtime behavior. The `COUNT_UPWIND_DIRECTION_FLIP` / `FIX_UPWIND_DIRECTION` options (`pm_subsurface_flow.F90:173-176`) are the diagnostics/mitigations available.
