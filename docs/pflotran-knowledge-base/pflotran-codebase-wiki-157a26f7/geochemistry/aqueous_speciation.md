**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** Aqueous speciation, thermodynamic database, activity coefficients, reaction convergence
**Last verified:** 2026-07-31

# Aqueous Speciation and the Thermodynamic Database

Owning files: `src/pflotran/reaction.F90` (6275 lines — parsing, speciation, activity coefficients, the local Newton solvers), `src/pflotran/reaction_aux.F90` (2012 — types, defaults, logK fitting/interpolation), `src/pflotran/reaction_database.F90` (3670 — `.dat` reader and basis setup), `src/pflotran/reaction_database_aux.F90` (387), `src/pflotran/reaction_equation.F90`, `src/pflotran/reaction_redox.F90`, `src/pflotran/reaction_gas.F90`.

---

## 1. Species classes and their deck blocks

All parsed in `ReactionReadPass1` (`src/pflotran/reaction.F90:112-971`); the `select case` is at `:186`. A second pass, `ReactionReadPass2` (`:975-…`), skips most of the same blocks.

| Deck block (verbatim literal) | Line | Meaning |
|---|---|---|
| `PRIMARY_SPECIES` | `src/pflotran/reaction.F90:188` | the basis. One transported component per entry; count in `reaction%naqcomp` (`:195`) |
| `SECONDARY_SPECIES` | `:212` | equilibrium aqueous complexes, eliminated algebraically. Count in `reaction%neqcplx` (`:219`) |
| `PASSIVE_GAS_SPECIES` | `:283` | gases in equilibrium with the aqueous phase, not transported |
| `ACTIVE_GAS_SPECIES` | `:264` | transported gas; requires the `GAS_TRANSPORT_IS_UNVETTED` acknowledgement card (`:270-276`) |
| `GAS_SPECIES` | `:281` | **deprecated** alias, errors to `PASSIVE_GAS_SPECIES` |
| `IMMOBILE_SPECIES` | `:287` | non-transported solid-phase species (biomass, etc.) |
| `MINERALS` | `:468` | see `mineral_kinetics.md` |
| `DATABASE` | `:756` | path to the thermodynamic database file |

Every primary and secondary species name must resolve against the database (`src/pflotran/reaction_database.F90:201-302`), except in `conservative_transport_only` mode.

---

## 2. Thermodynamic database format

Reader: `ReactionDBReadDatabase`, `src/pflotran/reaction_database.F90:22-793`. The file is opened at `:123` with `InputCreate(IUNIT_TEMP,reaction%database_filename,option)`. Setup into flat arrays is `ReactionDBInitBasis`, `:797-3113`. **This contract matters for any hand-modified `.dat`.**

### 2.1 Line 1 — temperature list

`src/pflotran/reaction_database.F90:125-144`:

```fortran
call InputReadPflotranString(input,option)
call InputReadQuotedWord(input,option,name,PETSC_TRUE)   ! comment, discarded
call InputReadInt(input,option,num_logKs)
...
  reaction%num_dbase_temperatures = num_logKs
  allocate(reaction%dbase_temperatures(reaction%num_dbase_temperatures))
  do itemp = 1, reaction%num_dbase_temperatures
    call InputReadDouble(input,option,reaction%dbase_temperatures(itemp))
```

Layout: `'<quoted comment>' <N> <T1> ... <TN>`. The quoted word is thrown away.

**Hard constraint (`src/pflotran/reaction_database.F90:146-166`):** unless `GEOTHERMAL_HPT` is on, PFLOTRAN aborts unless there are **exactly 8 temperatures equal to 0, 25, 60, 100, 150, 200, 250, 300 °C**, because the Debye-Hückel coefficient table is hardwired to those points. The error text is explicit (`:167-171`). A hand-edited database must keep this header verbatim.

### 2.2 Block structure

Blocks are separated by a record whose name is the literal `null`, counted in `num_nulls` (`src/pflotran/reaction_database.F90:168-199`). The in-source diagram at `:177-188`:

```
primary species / null / aq complexes / null / gases / null / minerals / null / surface complexes / null
```

Legacy format = **5** `null`s; `GEOTHERMAL_HPT` format = **4** (no surface-complex block) (`:191-198`). Dispatch: `case(0,1)` primary + secondary (`:202`), `case(2)` gases (`:304`), `case(3)` minerals (`:358`), `case(4)` surface complexes (`:377`).

### 2.3 Record column order

Every record begins with a **single-quoted name**. Column orders differ between classes — this is the most common hand-edit failure.

**Primary species** (`src/pflotran/reaction_database.F90:290-302`):
```
'name'  a0  Z  molar_weight[g/mol]
```
`a0` is the Debye-Hückel ion-size parameter, `Z` the charge. Molar weight is converted to kg/mol by `*1.d-3` (`:301`).

**Secondary aqueous complex** (`:261-302`):
```
'name'  nspec  (stoich_i 'primary_name_i')×nspec  logK_1..logK_N  a0  Z  molar_weight[g/mol]
```
Species count read at `:264`, stoich/name pairs `:272-281`, logKs `:283-286`.

**Gas** (`:322-356`) — note molar volume comes **before** the species count:
```
'name'  molar_volume[cm^3/mol]  nspec  (stoich 'name')×nspec  logK_1..logK_N  molar_weight[g/mol]
```
Molar volume `*1.d-6` → m³/mol (`:326`); molar weight `*1.d-3` (`:356`).

**Mineral** — dispatched at `:376`, read by `ReactionMnrlReadFromDatabase`, `src/pflotran/reaction_mineral.F90:831-890`:
```
'name'  molar_volume[cm^3/mol]  nspec  (stoich 'name')×nspec  logK_1..logK_N  molar_weight[g/mol]
```
```fortran
call InputReadDouble(input,option,mineral%molar_volume)          ! :856
mineral%molar_volume = mineral%molar_volume*1.d-6                ! :859
call InputReadInt(input,option,num_species_in_rxn)               ! :865
...
!note: logKs read are pK so that K is in the denominator (i.e. Q/K)
do itemp = 1, num_dbase_temperatures                             ! :880
  call InputReadDouble(input,option,mineral%dbaserxn%logK(itemp))
call InputReadDouble(input,option,mineral%molar_weight)          ! :885
mineral%molar_weight = mineral%molar_weight*1.d-3                ! :888
```

**Surface complex** (`:393-429`):
```
'name'  nspec(including the free site)  (stoich 'name')×nspec  logK_1..logK_N  Z
```
The count is decremented by one because the free site (name starting with `>`) is stored separately (`:399`, `:413-416`).

Points a hand-editor must respect:
- There is **no per-record logK count.** The count is global, from line 1. Adding a temperature point to one record silently corrupts the parse of everything after it.
- Molar volume and molar weight are read in **cm³/mol and g/mol** and converted internally. Writing SI values directly is a factor-10⁶/10³ error.
- The sign convention is stated in-source: `!note: logKs read are pK so that K is in the denominator (i.e. Q/K)` (`src/pflotran/reaction_mineral.F90:879`, and the same comment for aqueous complexes). Database logK is for the **dissolution/dissociation** direction as written.
- **`500.0` is the "undefined" sentinel.** `ReactionDBCheckLegitLogKs` (`src/pflotran/reaction_database_aux.F90:229-277`, test at `:263`) aborts if a species actually used in the problem has a 500 at the reference temperature; callers at `src/pflotran/reaction_database.F90:684, 707, 729, 751, 773`. A 500 in an unused record is harmless.
- Adding a mineral means adding it to the mineral block **before** the fourth `null`, and its stoichiometry must be written in terms of species that exist in the primary-species block.

### 2.4 logK versus temperature

Two representations.

**Legacy (`.dat`, 8 temperatures).** A 5-term least-squares fit is performed at setup by `ReactionAuxFitLogKCoef` (`src/pflotran/reaction_aux.F90:1137-1211`, attributed to P.C. Lichtner, 02/13/09). Basis functions (`:1167-1174`): `ln T`, `1`, `T`, `1/T`, `1/T²`, with `T` in Kelvin. Normal equations formed at `:1196-1206`, solved by `LUDecomposition`/`LUBackSubstitution` (`:1208-1209`). **Not a spline.**

Evaluation, `ReactionAuxInterpolateLogK` (`src/pflotran/reaction_aux.F90:1265-1292`):

$$\log K(T) = c_1\ln T + c_2 + c_3 T + \frac{c_4}{T} + \frac{c_5}{T^2},\qquad T\ [\mathrm{K}]$$

```fortran
logKs(i) = coefs(1,i)*log(temp_kelvin) &
         + coefs(2,i)           &
         + coefs(3,i)*temp_kelvin      &
         + coefs(4,i)/temp_kelvin      &
         + coefs(5,i)/(temp_kelvin*temp_kelvin)
```

`ReactionAuxInitializeLogK` (`:1215-1261`) short-circuits the fit and uses the tabulated value exactly when the reference temperature coincides with a database temperature (`:1243-1254`) — so a run at exactly 25 °C uses the raw database number, and a run at 20 °C uses the fit.

If `option%transport%isothermal_reaction` is true, no interpolation happens at all; the coefficient array keeps the raw tabulated values (`src/pflotran/reaction_database.F90:1674-1685`). Runtime re-interpolation is `RUpdateTempDependentCoefs` (`src/pflotran/reaction.F90:5760-5844`), called from `:3903-3905` inside the reaction Newton loop.

**`GEOTHERMAL_HPT`** (keyword at `src/pflotran/reaction.F90:765-766`). Line 1 is a parameter count (17 in the shipped `database/geothermal-hpt.dat`), the 17 numbers per record **are** the coefficients (no fit — `src/pflotran/reaction_database.F90:1747`), and evaluation is a 17-term function of reduced temperature `tr = T[K]/273.15` and reduced pressure `pr = P/1e7` in `ReactionAuxInterpolateLogK_hpt` (`src/pflotran/reaction_aux.F90:1331-1373`). Surface complexes are unsupported under HPT (`src/pflotran/reaction.F90:5838-5840`).

**No secondary/alternate reaction database exists at this commit** — there is exactly one `reaction%database_filename` slot (`src/pflotran/reaction_aux.F90:121`, default `''` at `:368`). A per-mineral override does exist: `OVERRIDE_MINERAL_MASS_ACTION` (`src/pflotran/reaction.F90:1023-1024` → `ReactionMnrlReadMassActOverride`, `src/pflotran/reaction_mineral.F90:584-682`) with sub-cards `REACTION` (`:643`) and `LOGK` (`:645`); the supplied logK count must be 1 or `num_dbase_temperatures` (`src/pflotran/reaction_database.F90:2272-2282`).

If `DATABASE` is omitted, activity coefficients are silently forced off (`src/pflotran/reaction.F90:968-969`).

---

## 3. Activity coefficients

**Exactly one model exists at this commit: extended Debye-Hückel with a B-dot term.** `PITZER` and `DAVIES` are NOT FOUND at this commit (`grep -rni "pitzer\|davies" src/pflotran/*.F90` yields only unrelated CO₂-EOS comments in `co2eos.F90`). There is no `DEBYE` deck keyword either — the model is unconditional.

Implementation: `RActivityCoefficients`, `src/pflotran/reaction.F90:4258-4504`. Both branches use the same formula (`:4384-4390` Newton branch, `:4465-4471` lag branch):

$$\log_{10}\gamma_i = \frac{-A z_i^2 \sqrt{I}}{1 + a_{0,i} B \sqrt{I}} + \dot{B}\,I$$

```fortran
rt_auxvar%pri_act_coef(icomp) = exp((-reaction%primary_spec_Z(icomp)* &
                              reaction%primary_spec_Z(icomp)* &
                              sqrt_I*reaction%debyeA/ &
                              (1.d0+reaction%primary_spec_a0(icomp)* &
                              reaction%debyeB*sqrt_I)+ &
                              reaction%debyeBdot*I)* &
                              LOG_TO_LN)
```

Neutral species get $\gamma = 1$ (`:4392`, `:4408`). Ionic strength $I = \tfrac12\sum_j m_j z_j^2$ over primary **and** secondary species (`:4447-4458`).

`A`, `B`, `Ḃ` come from a hardwired piecewise-linear table in temperature, `src/pflotran/reaction_database.F90:890-1000` (e.g. at ≤0.01 °C: `debyeA = 0.4939d0`, `debyeB = 0.3253d0`, `debyeBdot = 0.0374d0`, `:892-894`). **They are evaluated once from `option%transport%reference_temperature`, not per cell** — activity coefficients do not track a spatially varying temperature field even in a non-isothermal run.

`NO_BDOT` (`src/pflotran/reaction.F90:795-796`) zeroes `debyeBdot` (`src/pflotran/reaction_database.F90:1002-1004`), reducing the model to plain extended Debye-Hückel.

Water activity is optional (`ACTIVITY_H2O` / `ACTIVITY_WATER`, `src/pflotran/reaction.F90:826-827`) and uses a single hardwired empirical relation (`:4430`, `:4495`):

```fortran
rt_auxvar%ln_act_h2o = 1.d0-0.017d0*(sum_pri_molal+sum_sec_molal)
```

(then `log()`-ed at `:4432` / `:4497`). Without the card, $a_{\mathrm{H_2O}} = 1$.

### 3.1 `ACTIVITY_COEFFICIENTS` — algorithm and frequency

`src/pflotran/reaction.F90:773-794`. The card takes any number of sub-words on the same line; the first two lines of the case set the defaults-when-present (`LAG` + `TIMESTEP`).

| Sub-word | Line | Effect |
|---|---|---|
| `OFF` | `:780` | frequency = `ACT_COEF_FREQUENCY_OFF` |
| `TIMESTEP` | `:786` | update once per timestep |
| `NEWTON_ITERATION` | `:788` | update every Newton iteration |
| `LAG` | `:782` | algorithm = single-pass, ionic strength from current molalities |
| `NEWTON` | `:784` | algorithm = iterate ionic strength to self-consistency (≤ 50 iterations, `:4311`; tolerance `abs(I-II) < 1.d-6*I`, `:4332`) |

Enum values at `src/pflotran/reaction_aux.F90:23-27`. **Global defaults are `OFF` + `LAG`** (`src/pflotran/reaction_aux.F90:373-374`) — i.e. if you never write the card, activity coefficients are all 1. For a basalt column at appreciable ionic strength this is a first-order modelling choice, not a numerical detail.

---

## 4. `LOG_FORMULATION`

Parsed at `src/pflotran/reaction.F90:760-761`, one line, no argument, setting `reaction%use_log_formulation` (declared `src/pflotran/reaction_base.F90:12`, default `PETSC_FALSE` at `:35`). Three effects:

1. **Jacobian column scaling.** `RSolve`, `src/pflotran/reaction.F90:5290-5295`:
```fortran
if (use_log_formulation) then
  ! for derivatives with respect to ln conc
  do icomp = 1, ncomp
    Jac(:,icomp) = Jac(:,icomp)*conc(icomp)
  enddo
endif
```
2. **Multiplicative update with a step cap** instead of an additive one — constraint solve `:1929-1948`, reaction solve `:4038-4055`:
```fortran
update = dsign(1.d0,update)*min(dabs(update),reaction%max_dlnC)
rt_auxvar%pri_molal = rt_auxvar%pri_molal*exp(-update)
```
Concentrations therefore stay strictly positive by construction; the linear branch has to clamp them explicitly.
3. **The global transport solve is posed in ln C** (`src/pflotran/pm_rt.F90:528`, `:739`, `:1082-1091`).

A non-obvious detail: the *constraint* equilibration deliberately alternates log and linear updates on iterations 4–8 (`src/pflotran/reaction.F90:1899-1910`), with the in-source rationale that pure-log updates converge poorly for linear problems and tracers.

Companion step caps: `MAX_DLNC` (`:835-837`, default `5.d0` at `src/pflotran/reaction_aux.F90:511`) and `MAX_DLNC_RREACT` (`:838-840`, default `5.d0` at `:512`).

---

## 5. Convergence controls

| Deck keyword(s) | Parse line (`reaction.F90`) | Variable | Default | Where used |
|---|---|---|---|---|
| `MAX_RELATIVE_CHANGE_TOLERANCE`, `REACTION_TOLERANCE` | `:867` | `max_relative_change_tolerance` | `1.d-6` (`reaction_aux.F90:513`) | `:2024` (constraint), `:4086` (`RReact`) |
| `MAX_RESIDUAL_TOLERANCE` | `:872` | `max_residual_tolerance` | `1.d-12` (`reaction_aux.F90:514`) | `:2023`, `:4002` |
| *(no deck keyword)* | — | `max_rel_residual_tolerance` | `1.d-8` (`reaction_aux.F90:515`) | `:4003` |
| `MAXIMUM_REACTION_ITERATIONS` | `:892` | `maximum_reaction_iterations` | `20` (`reaction_aux.F90:409`) | `:3936` |
| `MAXIMUM_REACTION_CUTS` | `:889` | `maximum_reaction_cuts` | `10` (`reaction_aux.F90:408`) | `:3745`, `:3942-3943` |
| `MAX_DLNC` | `:835` | `max_dlnC` | `5.d0` | `:1930` |
| `MAX_DLNC_RREACT` | `:838` | `max_dlnC_rreact` | `5.d0` | `:4039` |
| `TRUNCATE_CONCENTRATION` | `:762` | `truncated_concentration` | uninitialized | `pm_rt.F90:1089-1091` |
| `DONT_STOP_ON_RREACT_FAILURE` | `:895` | `stop_on_rreact_failure` | `.true.` (`reaction_aux.F90:411`) | `:3752`, `:3988`, `:4022` |
| `NO_CHECK_UPDATE` | `:767` | `check_update` | `.true.` | `pmc_subsurface.F90:371`, `:495` — when true, registers PETSc's `SNESLineSearchSetPreCheck` on the global transport solve |
| `USE_TOTAL_CONCENTRATION_AS_GUESS` | `:897` | `use_total_as_guess` | `.false.` | `reaction.F90:3717-3720` — seeds `RStep`'s initial guess with total concentrations rather than the previous free-ion molalities |
| `LOGGING_VERBOSITY` | `:883` | `logging_verbosity` | `0` | `:3755`, `:3941`, `:4065` |

Notes for a calibration agent:
- The literal is `MAXIMUM_REACTION_ITERATIONS` (plural). `MAXIMUM_REACTION_ITERATION` is **NOT FOUND at this commit**.
- `max_rel_residual_tolerance` (1e-8) is **not settable from the deck** — it is hardwired at `src/pflotran/reaction_aux.F90:515`. Tightening `MAX_RESIDUAL_TOLERANCE` alone will not tighten the relative test at `:4003`.
- `MAX_RELATIVE_CHANGE_TOLERANCE` and `REACTION_TOLERANCE` are the *same* `case` (`:867`) — two spellings of one knob.
- Constraint equilibration has two additional hardwired guards: a warning every 1000 iterations (`:1998-2001`) and a hard stop at 10000 (`:2010-2018`).

---

## 6. The two Newton solvers

### 6.1 `ReactionEquilibrateConstraint` — `src/pflotran/reaction.F90:1373-2111`

Turns a `CONSTRAINT` block into free-ion molalities. Per iteration: reset free-ion dofs (`:1637-1642`), optionally update activity coefficients (`:1643-1649`), `RTotal` (`:1650`), then build one Jacobian row per component according to that component's constraint type (`select case` at `:1681`). Convergence requires **both** the residual and relative-change tests, and at least two iterations after activity coefficients are switched on (`:2022-2035`).

Constraint concentration types accepted in a `CONSTRAINT / CONCENTRATIONS` row (`src/pflotran/transport_constraint_rt.F90:306-346`; enum `:22-34`):

| Literal(s) | Line | Meaning |
|---|---|---|
| `F`, `FREE` | `:307` | free-ion molality |
| `T`, `TOTAL` | `:309` | total aqueous component concentration |
| `TOTAL_SORB` | `:311` | total sorbed |
| `TOTAL_AQ_PLUS_SORB` | `:314` | sum; requires equilibrium sorption (`:315-319`) |
| `P`, `PH` | `:327` | pH |
| `E`, `PE` | `:329` | pe |
| `L`, `LOG` | `:331` | log of free-ion molality |
| `M`, `MINERAL`, `MNRL` | `:333` | equilibrium with a named mineral |
| `G`, `GAS` | `:336` | equilibrium with a named gas at a partial pressure |
| `SC`, `CONSTRAINT_SUPERCRIT_CO2` | `:338` | supercritical CO₂ |
| `Z`, `CHARGE_BALANCE` | `:341` | close the charge balance on this component |
| `S` | `:323` | **removed** — fatal error since March 2013 |

Charge balance residual and Jacobian, `src/pflotran/reaction.F90:1721-1732`: $\sum_j z_j T_j = 0$ with $T_j$ the total component concentrations. If it drives a component negative, PFLOTRAN warns and resets that guess to 1e-3 (`:1733-1749`).

### 6.2 `RReact` — `src/pflotran/reaction.F90:3825-4100`

The per-cell reaction Newton solve, called from `RStep` (`:3645-3821`), which wraps it in sub-timestep cutting (cut counter and limit at `:3744-3745`). Per iteration: optional activity-coefficient update (`:3930-3933`), `RTAuxVarCompute` (`:3934`), accumulation residual (`:3966-3967`) and derivative (`:3969-3970`), divide by `option%tran_dt` (`:3972`), then all reaction source terms through `RReactionDerivative` (`:3974-3977`).

`RReaction` (`:4104-4193`) is the single dispatcher for every kinetic process: mineral kinetics `:4132`, multirate/kinetic surface complexation `:4138`, radioactive decay `:4150`, general reactions `:4156`, microbial `:4162`, immobile decay `:4168`, reaction sandbox `:4174`, carbon sandbox `:4180`, CLM reactions `:4187`. The linear solve is a dense LU in `RSolve` (`:5254-5305`) — the local system is `ncomp × ncomp`, so cost scales with the square/cube of the number of primary species. PETSc's `SNES`/`KSP` are used for the *global* transport system, not this local one.

---

## 7. Total component concentration

`RTotal` (`src/pflotran/reaction.F90:4508-4542`) dispatches to `RTotalAqueous` (`:4546-4638`), `RTotalSorb` (`:4662-4705`), and either `RCO2TotalCO2` or `ReactionGasTotalGas`.

In `RTotalAqueous`, each secondary complex is computed from mass action (`:4589-4603`):

$$m_k^{\mathrm{sec}} = \frac{1}{\gamma_k}\exp\!\Bigl[-\ln(10)\log K_k + \nu_{k,w}\ln a_{\mathrm{H_2O}} + \sum_j \nu_{kj}\ln a_j\Bigr]$$

then $T_j = m_j + \sum_k \nu_{kj} m_k^{\mathrm{sec}}$ (`:4608-4613`), with the analytical `dtotal` built alongside (`:4618-4628`). Totals and derivatives are converted from molality to **molarity** at the end (`:4631-4636`) by multiplying by `den_kg_per_L`. Residuals throughout PFLOTRAN's reactive transport are in mol/s; totals fed to transport are per litre of water.

pH, Eh, pe and $\ln f_{\mathrm{O_2}}$ are diagnostics only, computed in `src/pflotran/reaction_redox.F90` (`ReactionRedoxCalcpH` `:26-54`, `ReactionRedoxCalcEhpe` `:57`, `ReactionRedoxCalcLnFO2` `:114`, `ReactionRedoxCalcLogKEh` `:156`). pH is $-\log_{10}(m_{\mathrm{H^+}}\gamma_{\mathrm{H^+}})$ and works whether H⁺ is primary or secondary (`:42-51`). That module exports **no** deck keywords and no `select case` — it is pure post-processing. `REDOX_SPECIES` as a `CHEMISTRY` card is deprecated in favour of `DECOUPLED_EQUILIBRIUM_REACTIONS` (`src/pflotran/reaction.F90:828-830`).

Gases: `ReactionGasReadGas` (`src/pflotran/reaction_gas.F90:26`) reads a bare list of names with no sub-keywords; `ReactionGasTotalGas` (`:86`) adds active-gas contributions; `ReactionGasPartialPresToConc` (`:179`) converts a partial pressure to a concentration.

---

## 8. Calibration knobs summary

| Deck keyword | Source line | Units | Default | Controls |
|---|---|---|---|---|
| `DATABASE <file>` | `reaction.F90:756` | path | `''` | all logK values; omitting it silently disables activity coefficients |
| database `logK` column | `reaction_mineral.F90:880` (minerals), `reaction_database.F90:283` (complexes) | log₁₀, dissolution direction | from file | equilibrium constants; the primary lever on saturation state |
| `OVERRIDE_MINERAL_MASS_ACTION` / `LOGK` | `reaction_mineral.F90:645` | log₁₀ | none | per-mineral logK override without editing the `.dat` |
| database `a0` column | `reaction_database.F90:292` | Å (as used in the DH denominator) | from file | ion-size parameter in the activity model |
| `ACTIVITY_COEFFICIENTS [OFF\|LAG\|NEWTON][TIMESTEP\|NEWTON_ITERATION]` | `reaction.F90:773` | enum | `OFF` + `LAG` | whether activity corrections are applied at all |
| `NO_BDOT` | `reaction.F90:795` | flag | off (Ḃ used) | drops the B-dot term |
| `ACTIVITY_H2O` / `ACTIVITY_WATER` | `reaction.F90:826` | flag | off ($a_w=1$) | enables the empirical water-activity relation |
| `GEOTHERMAL_HPT` | `reaction.F90:765` | flag | off | switches to the 17-coefficient P-T database |
| `LOG_FORMULATION` | `reaction.F90:760` | flag | off | ln C Newton update; usually improves robustness |
| `MAX_RELATIVE_CHANGE_TOLERANCE` | `reaction.F90:867` | dimensionless | `1.d-6` | speciation convergence |
| `MAX_RESIDUAL_TOLERANCE` | `reaction.F90:872` | mol/s | `1.d-12` | speciation convergence |
| `MAXIMUM_REACTION_ITERATIONS` | `reaction.F90:892` | count | `20` | Newton iteration cap per reaction step |
| `MAXIMUM_REACTION_CUTS` | `reaction.F90:889` | count | `10` | sub-timestep cuts before failure |
| `MAX_DLNC` / `MAX_DLNC_RREACT` | `reaction.F90:835`/`:838` | ln units | `5.d0` | update step cap under `LOG_FORMULATION` |
| `TRUNCATE_CONCENTRATION` | `reaction.F90:762` | mol/L | uninitialized | floor applied to transported concentrations |
| `REFERENCE_TEMPERATURE` (transport) | consumed at `reaction_database.F90:891` | °C | see `option` defaults | picks the Debye-Hückel A/B/Ḃ triple and the logK reference point |

## 9. Things I could not verify

- Whether the hardwired empirical water activity `1 - 0.017·Σm` is intended to be valid at high ionic strength; it has no citation in source.
- The exact provenance of the Debye-Hückel table values in `reaction_database.F90:890-1000` (no reference in source).
- The `SECONDARY_SPECIES` deck block accepts a bare name list only; whether a secondary species named there but absent from the database is a hard error or a silent skip is not obvious from static reading of `reaction_database.F90:201-302`.
