**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** `MODE GENERAL` — governing equations, primary variables, thermodynamic state logic, and every `OPTIONS` sub-card
**Last verified:** 2026-07-31

---

## 1. What GENERAL solves

GENERAL is PFLOTRAN's two-phase (liquid + gas), two-component (water + air) non-isothermal flow mode. Files: `src/pflotran/general.F90` (driver: setup, residual, Jacobian assembly), `src/pflotran/general_aux.F90` (auxiliary variables, state logic, EOS calls), `src/pflotran/general_common.F90` (accumulation, internal flux, boundary flux, source/sink), `src/pflotran/general_derivative.F90` (analytical-derivative test harness), `src/pflotran/pm_general.F90` (process-model wrapper, input, convergence).

`PMGeneralSetFlowMode` (`pm_general.F90:111-301`) fixes the index conventions (`pm_general.F90:167-195`):

```
option%iflowmode        = G_MODE          (pm_general.F90:167)
option%liquid_phase     = 1               (:171)
option%gas_phase        = 2               (:172)
option%air_pressure_id  = 3               (:174)
option%capillary_pressure_id = 4          (:175)
option%vapor_pressure_id     = 5          (:176)
option%saturation_pressure_id = 6         (:177)
option%water_id = 1, option%air_id = 2    (:179-180)
```

Default sizing: `nphase = 2`, `nflowdof = 3`, `nflowspec = 2`, `energy_id = 3`, `general_max_states = 3` (`pm_general.F90:182-188`). With the `SOLUTE` option the mode becomes 4-dof: `nflowspec = 3`, `salt_id = 3`, `energy_id = 4`, `nphase = 3` (a precipitate phase), `general_max_states = 7` (`pm_general.F90:189-201`). Anything other than 3 or 4 dof is a fatal error (`pm_general.F90:202-207`).

## 2. Governing equations

Three residual equations per cell (four with `SOLUTE`), indexed by `GENERAL_LIQUID_EQUATION_INDEX = 1`, `GENERAL_GAS_EQUATION_INDEX = 2`, `GENERAL_ENERGY_EQUATION_INDEX = 3` (`general_aux.F90:96-99`). "Liquid equation" is the **water-component** mass balance and "gas equation" the **air-component** mass balance; both components live in both phases.

### Accumulation (`GeneralAccumulation`, `general_common.F90:50-412`)

Component mass, units kmol/s (`general_common.F90:95-122`):

$$R_{i}^{\text{accum}} = \frac{\phi\,V}{\Delta t}\sum_{\alpha=1}^{n_p} s_\alpha\,\rho_\alpha\,x_{i,\alpha}$$

with $\phi$ = `gen_auxvar%effective_porosity` (compressibility-corrected, `general_common.F90:93`), $V$ = `material_auxvar%volume` [m³], $s_\alpha$ = saturation [-], $\rho_\alpha$ = molar density [kmol/m³ phase], $x_{i,\alpha}$ = mole fraction [kmol comp/kmol phase].

Energy, units MJ/s (`general_common.F90:132-156`):

$$R_{e}^{\text{accum}} = \frac{V}{\Delta t}\left[\phi\sum_\alpha s_\alpha \rho_\alpha U_\alpha \;+\; (1-\phi)\,\rho_r\,c_r\,T\right]$$

$U_\alpha$ = phase internal energy [MJ/kmol], $\rho_r$ = `material_auxvar%soil_particle_density` [kg/m³ rock], $c_r$ = `soil_heat_capacity` [MJ/kg-K], $T$ in °C (`general_common.F90:149-156`).

### Internal flux (`GeneralFlux`, `general_common.F90:416-2485`)

Darcy advection per phase (`general_common.F90:642-653`):

$$v_\alpha = \frac{\bar k}{d}\,\frac{k_{r\alpha}}{\mu_\alpha}\,\Delta P_\alpha,\qquad
\Delta P_\alpha = P_\alpha^{up} - P_\alpha^{dn} + \bar\rho^{kg}_\alpha\,(\mathbf{g}\!\cdot\!\hat{\mathbf{d}})\,d$$

- `perm_ave_over_dist` is the distance-weighted harmonic permeability mean, $\bar k/d = k_{up}k_{dn}/(d_{up}k_{dn}+d_{dn}k_{up})$ (`general_common.F90:573-574`).
- `mobility` $= k_r/\mu$ is assigned at `general_aux.F90:1500` (liquid) and `:1534` (gas), with $\mu$ from `EOSWaterViscosity`/`EOSGasViscosity` in Pa·s. **Doc-comment defect:** the declaration comment at `general_aux.F90:154` says "relative perm / kinematic viscosity"; the code divides by dynamic viscosity. Trust the code.
- Gravity term: `dist_gravity = dist(0)*dot_product(option%gravity,dist(1:3))` then `gravity_term = density_kg_ave*dist_gravity` (`general_common.F90:597-600`). Note it uses **mass** density [kg/m³].
- Upwinding is by the sign of `delta_pressure` via `UpwindDirection` (`general_common.F90:615-632`); the upwind cell supplies mobility, mole fractions, enthalpy, and $k_r$.

Component and energy contributions (`general_common.F90:661-671`):

$$F_i = v_\alpha A\,\bar\rho_\alpha\,x_{i,\alpha},\qquad F_e = \sum_\alpha v_\alpha A\,\bar\rho_\alpha\,H_\alpha$$

Diffusion of the air component in **both** phases (`general_common.F90:1513-2042`), guarded by `if (.not.general_immiscible)` (`:1514`):

$$F^{\text{diff}}_{\text{air}} = \bar\rho\;\frac{(s\,\tau\,\phi\,\rho)_{up}(s\,\tau\,\phi\,\rho)_{dn}}{(s\tau\phi\rho)_{up}d_{dn}+(s\tau\phi\rho)_{dn}d_{up}}\;\cdot D_\alpha \cdot f_T \cdot A\cdot \Delta X$$

- $\tau$ = `material_auxvar%tortuosity`; $D_\alpha$ = `general_parameter%diffusion_coefficient(iphase)` (set from `FLUID_PROPERTY`, see §7).
- $\Delta X$ is a **mole**-fraction difference by default, a **mass**-fraction difference if `DIFFUSE_XMASS` is set (`general_common.F90:1587-1610`).
- $f_T$ (`diffusion_scale`) is 1 for the liquid phase; for the gas phase it is the temperature/pressure correction

  $$f_T = \left(\frac{T+273.15}{273.15}\right)^{1.8}\frac{101325}{\bar P_g}$$

  applied only when `general_temp_dep_gas_air_diff` is true (`general_common.F90:2014-2031`). `NO_TEMP_DEPENDENT_DIFFUSION` sets $f_T \equiv 1$.
- Water and air diffusive fluxes are equal and opposite: `Res(wat) -= tot_mole_flux; Res(air) += tot_mole_flux` (`general_common.F90:1625-1626`, `2041-2042`).

Heat conduction is added at the end of `GeneralFlux` and `GeneralBCFlux` using the thermal characteristic curve (`general_common.F90:3905-3937` for the BC branch; `k_{eff}` from `thermal_cc%thermal_conductivity_function%CalculateTCond`, converted J/s → MJ/s by `1.d-6`).

### Non-Darcy option

With `NON_DARCY_FLOW`, `GeneralNonDarcyCorrection` (`general_common.F90:5786-5822`) replaces the Darcy law with Liu (2014) eq. 3:

$$v = \mathrm{sign}\big(K[\,\nabla h + I(e^{-\nabla h/I}-1)\,],\ \Delta P\big),\quad I = A\,(\bar k k_r)^{B},\quad K = \tfrac{\bar k}{d}\tfrac{k_r}{\mu}\rho^{kg}g$$

with $A$ = `non_darcy_A` (default `4.0d-12`), $B$ = `non_darcy_B` (default `-0.78`), both from Liu (2014) eq. 11 (`general_aux.F90:35-36`). Units of $A$, $B$ are not stated in the source.

## 3. Primary variables and the thermodynamic state

GENERAL uses a **variable-switching** formulation. The state is an integer on the global auxvar, `global_auxvar%istate`, drawn from (`general_aux.F90:67-78`):

| Constant | Value | Line |
|---|---|---|
| `NULL_STATE` | 0 | `general_aux.F90:67` |
| `LIQUID_STATE` | 1 | `:68` |
| `GAS_STATE` | 2 | `:69` |
| `TWO_PHASE_STATE` / `LG_STATE` | 3 | `:70-71` |
| `P_STATE` | 4 | `:72` |
| `LP_STATE` | 5 | `:73` |
| `GP_STATE` | 6 | `:74` |
| `LGP_STATE` | 7 | `:75` |
| `ANY_STATE` | 8 | `:76` |
| `MULTI_STATE` | 9 | `:77` |

States 4–7 involve the precipitate phase and are only reachable with `SOLUTE` (4-dof). A 3-dof run uses 1, 2, 3 only.

The dof→meaning map, decoded in `GeneralAuxVarCompute` (`general_aux.F90:710-1134`):

| State | dof 1 | dof 2 | dof 3 |
|---|---|---|---|
| `LIQUID_STATE` | liquid pressure `x(GENERAL_LIQUID_PRESSURE_DOF=1)` [Pa] | air mole fraction in liquid `x(GENERAL_LIQUID_STATE_X_MOLE_DOF=2)` [-] | temperature `x(GENERAL_ENERGY_DOF=3)` [°C] |
| `GAS_STATE` | gas pressure `x(GENERAL_GAS_PRESSURE_DOF=1)` [Pa] | air pressure `x(GENERAL_GAS_STATE_AIR_PRESSURE_DOF=2)` [Pa] **or** water mole fraction in gas, per `GAS_STATE_AIR_MASS_DOF` | temperature [°C] |
| `TWO_PHASE_STATE` | gas pressure [Pa] | gas saturation `x(GENERAL_GAS_SATURATION_DOF=2)` [-] | temperature [°C] **or** air pressure, per `TWO_PHASE_STATE_ENERGY_DOF` |

Constants at `general_aux.F90:83-93`. Selector defaults: `general_2ph_energy_dof = GENERAL_TEMPERATURE_INDEX` (`general_aux.F90:129`), `general_gas_air_mass_dof = GENERAL_AIR_PRESSURE_INDEX` (`general_aux.F90:130`).

Per-state secondary closures worth knowing:
- `LIQUID_STATE`: $s_l = 1$, $s_g = 0$, $P_c = 0$ (`general_aux.F90:724-725`, `:801`); gas-phase mole fractions are zeroed (`:723`); air partial pressure from Henry's law $P_a = \tilde K_H x_{a,l}$ (`:782`); vapor pressure $P_v = P_l - P_a$ (`:799`). If gas pressure goes non-positive PFLOTRAN prints a bailout message and reconstructs $P_v = 0.5 P_{sat}$ (`general_aux.F90:787-797`).
- `GAS_STATE`: $s_l = 0$, $s_g = 1$ (`:830-831`); capillary pressure is still evaluated from the saturation function at $s_l = 0$ (`:834-836`) so that a free-surface boundary behaves.
- `TWO_PHASE_STATE`: $P_c$ from the saturation function at $s_l = 1-s_g$ (`:974-976`); $P_l = P_g - P_c$ (`:1101`); $P_v = P_{sat}(T)$ and $P_a = P_g - P_v$ (`:1058-1059`); air mole fraction in liquid $x_{a,l} = P_a/\tilde K_H$ (`:1103`).

An unrecognized `istate` is a fatal error (`general_aux.F90:1128-1132`).

## 4. Phase appearance and disappearance (state transitions)

`GeneralAuxVarUpdateState` (`general_aux.F90:2883-3117`) is the switching logic for 3-dof; `GeneralAuxVarUpdateState4` (`:3121-3711`) is the 4-dof analogue. It returns immediately if `general_immiscible` is set, or if the cell already flagged a state change this iteration (`general_aux.F90:2921`).

**Trigger conditions** (`general_aux.F90:2944-3045`):

| From | Test | To |
|---|---|---|
| `LIQUID_STATE` | $P_v \le P_{sat}\,(1-\varepsilon_w)$ | `TWO_PHASE_STATE` (gas appears) |
| `GAS_STATE` | $P_v \ge P_{sat}\,(1+\varepsilon_w)$ | `TWO_PHASE_STATE` (liquid appears) |
| `TWO_PHASE_STATE` | $s_g^{new} < 0$ | `LIQUID_STATE` (gas disappears) |
| `TWO_PHASE_STATE` | $s_g^{new} > 1$ | `GAS_STATE` (liquid disappears) |

$\varepsilon_w$ = `window_epsilon`, default `1.d-4` (`general_aux.F90:29`), settable by `WINDOW_EPSILON`. Note the commented-out alternative test at `general_aux.F90:2948-2950` — the shipped liquid→2-phase test uses only the vapor-pressure criterion, not the air-pressure one.

**Primary-variable reset on transition** (`general_aux.F90:3048-3101`). After switching, the dof vector is rewritten to the new state's meaning and `GeneralAuxVarCompute` is re-called (`:3103`):

- → `LIQUID_STATE`: $x_1 = P_l$, $x_2 = \max(0, x_{a,l})$, $x_3 = T$.
- → `GAS_STATE`: $x_1 = P_g$, $x_2 = P_a$ (or $x_{w,g}$), $x_3 = T$.
- → `TWO_PHASE_STATE` **from gas**: $s_g$ is seeded at $1-\varepsilon_p$ (`:3070`).
- → `TWO_PHASE_STATE` **from liquid**: $P_g = \max(P_g, P_{sat})$ and $s_g$ seeded at $\varepsilon_p$ (`:3072-3074`).

$\varepsilon_p$ = `general_phase_chng_epsilon`, default `1.d-6` (`general_aux.F90:17`), settable by `PHASE_CHANGE_EPSILON`. **This is the single most important knob for two-phase appearance robustness.** Too small and the newly appeared phase has essentially zero mobility; too large and mass is injected at the switch.

Every transition prints `State Transition: <From> -> <To> at Cell <id>` via `PrintMsgByRank` unless `NO_STATE_TRANSITION_OUTPUT` is set (`general_aux.F90:3105-3108`, `general_print_state_transition` default `PETSC_TRUE` at `:13`). The message distinguishes cells (`GENERAL_UPDATE_FOR_ACCUM`), perturbation-induced changes (`GENERAL_UPDATE_FOR_DERIVATIVE`), and boundary faces (`general_aux.F90:2958-2968`). **A log full of transitions at the same cells is the signature of state chatter; the fixes are `RESTRICT_STATE_CHANGE` and a larger `WINDOW_EPSILON`.**

`RESTRICT_STATE_CHANGE` sets `gen_auxvar%istatechng = PETSC_TRUE` on the first change (`general_aux.F90:3050`), which both blocks any further change for that cell (via the early return at `:2921`) and clamps $s_g$ into $[0,1]$ in `GeneralAuxVarCompute` (`general_aux.F90:967-970`).

## 5. Every `OPTIONS` sub-card of `SUBSURFACE_FLOW` `MODE GENERAL`

Read by `PMGeneralReadSimOptionsBlock` (`pm_general.F90:304-496`). Cards inherited from `PMBaseReadSimOptionsSelectCase` and `PMSubsurfFlowReadSimOptionsSC` are listed in `mode_selection.md` §4; the GENERAL-specific `select case` is `pm_general.F90:357-484`. Anything unmatched aborts (`pm_general.F90:482-483`).

| Keyword | Line | Arg | Sets | Default | Effect / side effects |
|---|---|---|---|---|---|
| `ARITHMETIC_GAS_DIFFUSIVE_DENSITY` | `:360` | — | `general_harmonic_diff_density=F` | harmonic (`general_aux.F90:46`) | Diffusive density averaged arithmetically (upstream-weighted across unequal states) instead of harmonically (`general_common.F90:1546-1569`) |
| `CALCULATE_SURFACE_TENSION` | `:422` | — | `general_compute_surface_tension=T` | F (`general_aux.F90:59`) | Scales $P_c$ by $\sigma(T)$ from `EOSWaterSurfaceTension` (`general_aux.F90:840-843`, `:980-983`). **Incompatible with analytical derivatives** — hard error (`general_aux.F90:701-708`) |
| `CENTRAL_DIFFERENCE_JACOBIAN` | `:456` | — | `general_central_diff_jacobian=T` | F (`general_aux.F90:26`) | Allocates 2×ndof perturbation auxvars for central differencing (`general.F90:153-161`) |
| `CHECK_MAX_DPL_LIQ_STATE_ONLY` | `:362` | — | `gen_chk_max_dpl_liq_state_only=T` | F (`general_aux.F90:57`) | Restricts the max-pressure-change check to liquid-state cells |
| `DEBUG_CELL` | `:364` | int | `general_debug_cell_id` | uninitialized (`general_aux.F90:34`) | Verbose per-cell diagnostics |
| `DIFFUSE_XMASS` | `:358` | — | `general_diffuse_xmol=F` | `PETSC_TRUE` (`general_aux.F90:44`) | Diffusive driving force becomes a **mass**-fraction gradient instead of mole-fraction (`general_common.F90:1587-1610`). Not implemented for 4-dof salt (`general_common.F90:3438-3442`) |
| `GAS_COMPONENT_FORMULA_WEIGHT` | `:367` | real | `fmw_comp(2)` | `FMWAIR` (`general_aux.F90:30`) | Air component formula weight [g/mol]; enters mass-fraction conversion and the gravity term |
| `GAS_STATE_AIR_MASS_DOF` | `:371` | `AIR_PRESSURE` \| `WATER_MOL_FRAC` | `general_gas_air_mass_dof` | `AIR_PRESSURE` (`general_aux.F90:130`) | Chooses dof 2 in `GAS_STATE` (`GeneralAuxSetAirMassDOF`, `general_aux.F90:541-566`). Also relaxes the dof-2 update tolerance in gas state (`pm_general.F90:296-299`) |
| `HARMONIC_GAS_DIFFUSIVE_DENSITY` | `:376` | — | `general_harmonic_diff_density=T` | T | Explicit restatement of the default |
| `IMMISCIBLE` | `:382` | — | `general_immiscible=T` | F (`general_aux.F90:15`) | See §6 |
| `ISOTHERMAL` | `:384` | — | `option%flow%isothermal=T` | F (`option_flow.F90:163`) | See §6 |
| `LIQUID_COMPONENT_FORMULA_WEIGHT` | `:396` | real | `fmw_comp(1)` | `FMWH2O` | Water component formula weight [g/mol] |
| `MIN_CENTRAL_DIFFERENCE_PERT` | `:458` | real | `general_min_cd_pert` | `1.d-7` (`general_aux.F90:18`) | Floor on the central-difference perturbation |
| `MIN_LIQUID_SATURATION` | `:462` | real | `general_min_liq_sat` **and** `general_prevent_gp_phase=T` | uninitialized / F (`general_aux.F90:19,27`) | **Silent side effect:** also turns on the gas-precipitate-phase guard |
| `MIN_PERMEABILITY` | `:446` | real | `general_min_permeability` | `1.d-25` (`general_aux.F90:135`) | Floor when `UPDATE_PERMEABILITY` is active [m²] |
| `MIN_POROSITY` | `:467` | real | `general_min_porosity` **and** `general_min_porosity_flag=T` | `1.d-12` / F (`general_aux.F90:20-21`) | |
| `NEWTONTRDC_HOLD_INNER_ITERATIONS` (aliases `HOLD_INNER_ITERATIONS`, `NEWTONTRDC_HOLD_INNER`) | `:378-379` | — | `general_newtontrdc_hold_inner=T` | F (`general_aux.F90:56`) | Only meaningful with the `newtontrd-c` solver |
| `NO_AIR` | `:400` | — | `general_no_air=T` | F (`general_aux.F90:131`) | Zeroes the **gas (air) equation** residual (`general.F90:1713-1719`) and its Jacobian row (`general.F90:2100-2111`) / row+column in the numerical path (`general.F90:2516-2519`). Allocates the zeroing array (`general.F90:207`) |
| `NO_STATE_TRANSITION_OUTPUT` | `:402` | — | `general_print_state_transition=F` | T (`general_aux.F90:13`) | Silences the per-cell transition messages |
| `NO_TEMP_DEPENDENT_DIFFUSION` | `:404` | — | `general_temp_dep_gas_air_diff=F` | `PETSC_TRUE` (`general_aux.F90:45`) | See §6 |
| `NON_DARCY_FLOW` | `:386` | — | `general_non_darcy_flow=T` | F (`general_aux.F90:16`) | Liu (2014) threshold-gradient law replaces Darcy (`general_common.F90:5786`) |
| `NON_DARCY_FLOW_A` | `:388` | real | `non_darcy_A` | `4.0d-12` (`general_aux.F90:35`) | Liu (2014) eq. 11 coefficient |
| `NON_DARCY_FLOW_B` | `:392` | real | `non_darcy_B` | `-0.78` (`general_aux.F90:36`) | Liu (2014) eq. 11 exponent |
| `PHASE_CHANGE_EPSILON` | `:406` | real | `general_phase_chng_epsilon` | `1.d-6` (`general_aux.F90:17`) | Saturation seeded into a newly appearing phase |
| `RESTRICT_STATE_CHANGE` | `:410` | — | `general_restrict_state_chng=T` | F (`general_aux.F90:25`) | One state change per cell per iteration; also clamps $s_g\in[0,1]$ |
| `SALT_SOURCE_MAX_PRESSURE` | `:477` | real | `general_max_pres_srcsink` **and** `general_salt_src_flag=T` | `1.d15` / F (`general_aux.F90:23-24`) | 4-dof only |
| `SALT_SOURCE_MIN_POROSITY` | `:472` | real | `general_min_por_srcsink` **and** `general_salt_src_flag=T` | `1.d-6` / F | 4-dof only |
| `SOLUBLE_MATERIALS` | `:426` | word list | `pm%soluble_materials` | none | Names of material types treated as soluble matrix |
| `SOLUTE` | `:449` | word | `general_salt=T`, `general_set_solute=T`, **`option%nflowdof = 4`** | 3 dof | **Promotes GENERAL to 4 dof.** Adds precipitate phase and salt equation. `GeneralAuxSetSolute`, `general_aux.F90:2732-2763` |
| `TWO_PHASE_ENERGY_DOF` | `:412` | — | — | — | **Deprecated**, redirects to `TWO_PHASE_STATE_ENERGY_DOF` (`pm_general.F90:413-414`) |
| `TWO_PHASE_STATE_ENERGY_DOF` | `:415` | `TEMPERATURE` \| `AIR_PRESSURE` | `general_2ph_energy_dof` | `TEMPERATURE` (`general_aux.F90:129`) | Chooses dof 3 in two-phase state (`GeneralAuxSetEnergyDOF`, `general_aux.F90:509-537`). With `AIR_PRESSURE`, $T$ is back-solved from `EOSWaterSaturationTemperature` (`general_aux.F90:1065-1072`) |
| `UPDATE_PERMEABILITY` | `:442` | real | `general_update_permeability=T`, `permeability_func_porosity_exp` | F / `1.d0` (`general_aux.F90:133-134`) | Permeability follows porosity with the given exponent |
| `VAPOR_PRESSURE_KELVIN` | `:424` | — | `general_kelvin_equation=T` | F (`general_aux.F90:58`) | Kelvin correction to $P_{sat}$ via `EOSWaterKelvin` (`general_aux.F90:1005-1006`). **Incompatible with analytical derivatives** (`:701-708`) and requires `TWO_PHASE_STATE_ENERGY_DOF TEMPERATURE` (`general_aux.F90:1073-1078`) |
| `WINDOW_EPSILON` | `:419` | real | `window_epsilon` | `1.d-4` (`general_aux.F90:29`) | Dead-band on the $P_v$ vs. $P_{sat}$ state test |

**Cross-option validation:** `ISOTHERMAL` combined with `TWO_PHASE_STATE_ENERGY_DOF AIR_PRESSURE` is a fatal error (`pm_general.F90:489-494`). `SOLUTE` must be declared before the 4-dof branch runs, else *"Solute must be acknowledged in the OPTIONS block of GENERAL MODE"* (`pm_general.F90:197-201`).

**Preprocessor caveat:** when PFLOTRAN is built with `-DMATCH_TOUGH2`, three defaults flip — `general_temp_dep_gas_air_diff` and `general_diffuse_xmol` become `PETSC_FALSE` (`general_aux.F90:39-42`). The table above lists the **non-TOUGH2** defaults (`general_aux.F90:43-47`), which is the normal build.

## 6. The three options in the basalt-column deck, in detail

### `ISOTHERMAL`

Sets `option%flow%isothermal = PETSC_TRUE` (`pm_general.F90:385`). It does **not** remove the energy dof. `nflowdof` stays 3; temperature remains primary variable 3 and is still read from `FLOW_CONDITION`. Instead:

- The energy **residual** row is zeroed after assembly, for every local cell (`general.F90:1705-1712`).
- The energy **Jacobian** row is zeroed with the PETSc call `MatZeroRowsLocal` (external PETSc framework) using the index array allocated at `general.F90:207-210` (`general.F90:2087-2098`).
- In the numerical-Jacobian path, both the energy row and the energy column of the local block are zeroed (`general.F90:2512-2515`).

Net effect: temperature is frozen at its initial/boundary value everywhere, but all temperature-dependent EOS calls (density, viscosity, $P_{sat}$, Henry's constant, surface tension) still execute at that temperature. **You cannot omit `TEMPERATURE` from a GENERAL flow condition even when isothermal** — the condition verifier demands it (`condition.F90:2397-2401`).

Also note the state-transition code skips the temperature rescale under isothermal (`general_aux.F90:3077-3081`).

### `IMMISCIBLE`

Sets `general_immiscible = PETSC_TRUE` (`pm_general.F90:383`). Three separate effects:

1. **No state transitions at all.** `GeneralAuxVarUpdateState` returns on entry (`general_aux.F90:2921`), as does the 4-dof version (`:3161`). Every cell keeps whatever state it was initialized in for the whole run.
2. **No inter-phase mass exchange in the auxvars.** In two-phase, $P_{sat}$ is overwritten with `GENERAL_IMMISCIBLE_VALUE = 1.d-10` (`general_aux.F90:124`, applied at `:1055-1057`, `:1917-1918`, `:2264-2265`) and the dissolved-air mole fraction $x_{a,l}$ is pinned to the same `1.d-10` (`general_aux.F90:1104-1106`, `:1971-1972`, `:2297-2298`).
3. **Diffusion is switched off entirely.** The whole `#ifdef DIFFUSION` body of both `GeneralFlux` and `GeneralBCFlux` is wrapped in `if (.not.general_immiscible)` (`general_common.F90:1514-2387` and `:3372-3898`).

Boundary and initial conditions follow suit: `hydrostatic.F90:140-141` substitutes `GENERAL_IMMISCIBLE_VALUE` for the datum concentration, and `patch.F90` uses it for BC mole fractions and derives `air_pressure = gas_pressure - GENERAL_IMMISCIBLE_VALUE` (`patch.F90:1830-1831`, `:1923-1924`, `:2009-2010`, `:2069-2070`, `:2133-2134`, `:2226-2227`, `:2280-2281`).

**Practical consequence for a basalt column:** with `IMMISCIBLE`, water vapor and dissolved air are effectively absent, evaporation cannot occur, and a cell initialized two-phase stays two-phase regardless of how the pressures evolve. This makes the run far more robust but removes the vapor-transport physics.

### `NO_TEMP_DEPENDENT_DIFFUSION`

Sets `general_temp_dep_gas_air_diff = PETSC_FALSE` (`pm_general.F90:405`). Its only effect is in the **gas-phase** diffusion block: `diffusion_scale` becomes `1.d0` and its four derivatives become zero (`general_common.F90:2025-2031`; the BC analogue is `general_common.F90:3698`). Without it, the gas-phase diffusion coefficient is multiplied by $((T+273.15)/273.15)^{1.8}\cdot(101325/\bar P_g)$ (`general_common.F90:2014-2024`), the standard Millington/TOUGH2-style correction. The liquid-phase diffusion block has no such scale factor (`general_common.F90:1613-1615`) and is unaffected.

With `ISOTHERMAL` the temperature part of that factor is constant anyway, but the pressure part is **not** — so `NO_TEMP_DEPENDENT_DIFFUSION` is still a live change in an isothermal run. It is also, incidentally, an interaction with `IMMISCIBLE`: if `IMMISCIBLE` is on, diffusion is skipped entirely and this option has no effect at all.

## 7. EOS coupling

GENERAL calls the EOS modules directly from `GeneralAuxVarCompute` / `GeneralAuxVarCompute4`. Call inventory from `general_aux.F90` (counts by `grep -o "call EOS[A-Za-z]*"`):

| Routine | Purpose | Example site |
|---|---|---|
| `EOSGasHenry` (23×) | Henry's constant $\tilde K_H$ for air-in-water | `general_aux.F90:733`, `:743`, `:1008` |
| `EOSWaterSaturationPressure` / `…Ext` (9× / 14×) | $P_{sat}(T)$, salinity-aware variant | `:729`, `:739`, `:762` |
| `EOSWaterDensity` / `…Ext` | liquid density [kg/m³, kmol/m³] | `:868`, `:1002` |
| `EOSWaterEnthalpy` / `…Ext` | liquid $H$ [MJ/kmol] | (4× / 2×) |
| `EOSWaterViscosity` / `…Ext` | $\mu_l$ [Pa·s] | `:1471`, `:1491` |
| `EOSWaterSteamDensityEnthalpy` | vapor properties | (4×) |
| `EOSWaterSaturationTemperature` | $T$ from $P_{sat}$ when air pressure is the two-phase energy dof | `:1070` |
| `EOSWaterSurfaceTension` | $\sigma(T)$ for `CALCULATE_SURFACE_TENSION` | `:841`, `:981` |
| `EOSWaterKelvin` | Kelvin $P_{sat}$ correction | `:1005`, `:1048` |
| `EOSWaterComputeSalinity` | salinity when `sat_pres_depends_on_salinity` | `:759`, `:1024` |
| `EOSGasDensityEnergy` | air density, $U$, $H$ | (4×) |
| `EOSGasViscosity` | $\mu_g$ [Pa·s] | `:1524`, `:1532` |
| `EOSPrecipitateEnergy` | 4-dof precipitate | `general_aux.F90:4712` |

Henry failures are trapped and reported by `GeneralEOSGasError` (`general_aux.F90:2812-2844`).

These routines are configured by the top-level `EOS` card, read by `EOSRead` (`src/pflotran/eos.F90:39`). The two blocks that matter for GENERAL:

- `EOS WATER` (`eos.F90:76`) with sub-cards `DENSITY` (`:95`), `ENTHALPY` (`:179`), `VISCOSITY` (`:198`), `SATURATION_PRESSURE` (`:262`), `STEAM_DENSITY`, `STEAM_ENTHALPY`, `SALINITY`, `SURFACE_DENSITY`/`STANDARD_DENSITY`, `WATERTAB`, `TEST`.
- `EOS GAS` (`eos.F90:349`) with `DENSITY` (`:365`), `ENTHALPY` (`:447`), `VISCOSITY` (`:467`), `HENRYS_CONSTANT` (`:484`), `FORMULA_WEIGHT` (`:557`), `SURFACE_DENSITY`/`STANDARD_DENSITY`, `DATABASE`, `CO2_DATABASE`, `PVDG`, `CO2_SPAN_WAGNER_DB`, `TEST`.

**Diffusion coefficients do not come from `EOS`.** They come from `FLUID_PROPERTY` blocks (`factory_subsurface_read.F90:1538-1544`, reader `src/pflotran/fluid.F90:70-…`), one per phase, harvested into `general_parameter%diffusion_coefficient(phase_id)` in `GeneralSetup` (`general.F90:213-225`). The phase is selected by `PHASE LIQUID` or `PHASE GAS` (`fluid.F90:106-107`; mapped to `phase_id` at `realization_subsurface.F90:1010-1016`), and the value by `DIFFUSION_COEFFICIENT` (alias `LIQUID_DIFFUSION_COEFFICIENT`, `fluid.F90:109`). Note that the separate `GAS_DIFFUSION_COEFFICIENT` field (`fluid.F90:131`) is a **different** struct member and is *not* what GENERAL reads — to set the gas-phase diffusivity for GENERAL you need a second `FLUID_PROPERTY` block with `PHASE GAS` and `DIFFUSION_COEFFICIENT`. Missing either phase's coefficient is a fatal `UninitializedMessage` (`general.F90:226-238`).

## 8. Gravity

`option%gravity` is a 3-vector, defaulted to $(0,0,-9.8068)$ m/s² in `OptionCreate` (`src/pflotran/option.F90:532-533`; `EARTH_GRAVITY = 9.8068d0` at `src/pflotran/pflotran_constants.F90:98`). It is overridden by the `GRAVITY` card **inside the `GRID` block**, which takes three components (`src/pflotran/discretization.F90:472-483`):

```
GRID
  GRAVITY 0.d0 0.d0 -9.8068d0
END
```

`INVERT_Z_AXIS` on a structured grid negates the z-component after the block is read (`discretization.F90:604-606`) — a silent sign flip worth checking if a column drains upward.

GENERAL consumes gravity only through `dist_gravity = dist(0)*dot_product(option%gravity,dist(1:3))` in the flux routines (`general_common.F90:597`, `:2661`). The non-Darcy correction instead hardcodes `EARTH_GRAVITY` (`general_common.F90:5804`, `:5844`), so a modified `GRAVITY` card is ignored there.

## 9. Calibration knobs specific to GENERAL

Boundary conditions and their knobs are in `boundary_conditions.md`; characteristic curves, permeability, porosity, and tortuosity belong to the material-properties topic.

| Keyword | Block | Source line | Units | Default | Controls |
|---|---|---|---|---|---|
| `PHASE_CHANGE_EPSILON` | `SUBSURFACE_FLOW/OPTIONS` | `pm_general.F90:406` | – (saturation) | `1.d-6` | Saturation seeded into an appearing phase |
| `WINDOW_EPSILON` | `SUBSURFACE_FLOW/OPTIONS` | `pm_general.F90:419` | – (relative) | `1.d-4` | Dead-band on $P_v$/$P_{sat}$ state test |
| `NON_DARCY_FLOW_A` | `SUBSURFACE_FLOW/OPTIONS` | `pm_general.F90:388` | not stated | `4.0d-12` | Liu (2014) threshold-gradient coefficient |
| `NON_DARCY_FLOW_B` | `SUBSURFACE_FLOW/OPTIONS` | `pm_general.F90:392` | – | `-0.78` | Liu (2014) exponent |
| `MIN_LIQUID_SATURATION` | `SUBSURFACE_FLOW/OPTIONS` | `pm_general.F90:462` | – | uninitialized | Liquid-saturation floor (also sets the GP-phase guard) |
| `MIN_POROSITY` | `SUBSURFACE_FLOW/OPTIONS` | `pm_general.F90:467` | – | `1.d-12` | Porosity floor |
| `MIN_PERMEABILITY` | `SUBSURFACE_FLOW/OPTIONS` | `pm_general.F90:446` | m² | `1.d-25` | Permeability floor under `UPDATE_PERMEABILITY` |
| `UPDATE_PERMEABILITY <exp>` | `SUBSURFACE_FLOW/OPTIONS` | `pm_general.F90:442` | – | off / exp `1.d0` | $k(\phi)$ exponent |
| `GAS_COMPONENT_FORMULA_WEIGHT` | `SUBSURFACE_FLOW/OPTIONS` | `pm_general.F90:367` | g/mol | `FMWAIR` | Air molar mass |
| `LIQUID_COMPONENT_FORMULA_WEIGHT` | `SUBSURFACE_FLOW/OPTIONS` | `pm_general.F90:396` | g/mol | `FMWH2O` | Water molar mass |
| `DIFFUSION_COEFFICIENT` | `FLUID_PROPERTY` (`PHASE LIQUID`) | `fluid.F90:109` | m²/s | `1.d-9` (`fluid.F90:58`) | Liquid-phase air diffusivity |
| `DIFFUSION_COEFFICIENT` | `FLUID_PROPERTY` (`PHASE GAS`) | `fluid.F90:109` | m²/s | `1.d-9` (`fluid.F90:58`) | Gas-phase air diffusivity (base, before $f_T$) |
| `GRAVITY x y z` | `GRID` | `discretization.F90:472` | m/s² | `(0,0,-9.8068)` | Body force in the Darcy $\Delta P$ |
| `REFERENCE_PRESSURE` | `SUBSURFACE` | `factory_subsurface_read.F90:1369` | Pa | `101325` (`option_flow.F90:143`) | Reference pressure (used by RICHARDS/TH for $P_c$; GENERAL uses explicit phase pressures) |
| `MAXIMUM_PRESSURE_CHANGE` | `NUMERICAL_METHODS FLOW/NEWTON_SOLVER` | `pm_general.F90:667` | Pa | `5.d4` (`general_aux.F90:31`) | Newton update clamp on pressure |
| `MAX_ITERATION_BEFORE_DAMPING` | same | `pm_general.F90:670` | iterations | uninitialized (`general_aux.F90:32`) | When damping engages |
| `DAMPING_FACTOR` | same | `pm_general.F90:673` | – | `0.6` (`general_aux.F90:33`) | Newton update damping |
| `RESIDUAL_INF_TOL` (sets both abs and scaled) | same | `pm_general.F90:549` | – | see below | Blanket residual tolerance |
| `RESIDUAL_ABS_INF_TOL` | same | `pm_general.F90:556` | kmol/s (mass), MJ/s (energy) | `1.d-5` each (`pm_general.F90:149-152`) | Absolute residual convergence |
| `RESIDUAL_SCALED_INF_TOL` | same | `pm_general.F90:574` | – | `1.d-6` (`pm_general.F90:235`) | Scaled residual convergence |
| `LIQUID_`/`GAS_`/`ENERGY_RESIDUAL_ABS_INF_TOL` | same | `pm_general.F90:560`,`:563`,`:566` | as above | as above | Per-equation variants |
| `UPDATE_INF_TOL` (sets both abs and rel) | same | `pm_general.F90:589` | – | see below | Blanket update tolerance |
| `ABS_UPDATE_INF_TOL` and per-variable forms (`PRES_`, `TEMP_`, `SAT_`, `XMOL_`, `LIQUID_PRES_`, `GAS_PRES_`, `AIR_PRES_`) | same | `pm_general.F90:596-627` | Pa / °C / – / – | `1.d0` / `1.d-5` / `1.d-5` / `1.d-9` (`pm_general.F90:137-140`) | Absolute update convergence |
| `REL_UPDATE_INF_TOL` and per-variable forms | same | `pm_general.F90:634-666` | – | `1.d-3` (`pm_general.F90:143-146`) | Relative update convergence |

The per-state tolerance matrices are assembled in `PMGeneralSetFlowMode` (`pm_general.F90:222-244` for 3 dof, `:245-284` for 4 dof); the column index is the state (1 = liquid, 2 = gas, 3 = two-phase), which is why e.g. `SAT_ABS_UPDATE_INF_TOL` writes `abs_update_inf_tol(2,3)` (`pm_general.F90:611`) — dof 2 in the two-phase state only.

## 10. Known limitations at this commit

- Analytical derivatives for the `AIR_PRESSURE` two-phase energy dof are declared buggy in-source: *"Please use numerical derivatives until the bug is resolved"* (`general_aux.F90:940-942`).
- Analytical derivatives for the three seepage/conductance BC types abort at runtime if the seepage clamp fires (`general_common.F90:2716-2722`, `:2729-2733`).
- Mass-based diffusion (`DIFFUSE_XMASS`) is not implemented with `SOLUTE` (`general_common.F90:3442`).
- Capillary-pressure derivative w.r.t. saturation is taken from the characteristic curve, with a finite-difference alternative left in a disabled `#if 0` (`general_aux.F90:1087-1097`).
- `NON_DARCY_FLOW` uses hardcoded `EARTH_GRAVITY`, ignoring the `GRAVITY` card.
