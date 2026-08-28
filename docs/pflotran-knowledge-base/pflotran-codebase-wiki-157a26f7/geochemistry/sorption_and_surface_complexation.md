**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** Sorption — surface complexation, isotherms, ion exchange, dynamic Kd
**Last verified:** 2026-07-31

# Sorption and Surface Complexation

Owning files: `src/pflotran/reaction_surf_complex.F90` (1183 lines), `src/pflotran/reaction_surf_complex_aux.F90` (646), `src/pflotran/reaction_isotherm.F90` (354), `src/pflotran/reaction_isotherm_aux.F90` (220). **Ion exchange and dynamic Kd have no dedicated file** — they are parsed inline in `src/pflotran/reaction.F90` and evaluated there too.

All four sorption models live inside a `CHEMISTRY / SORPTION` block and are summed by one dispatcher, `RTotalSorb` (`src/pflotran/reaction.F90:4662-4705`): surface complexation `:4686`, ion exchange `:4691`, dynamic Kd `:4695`, isotherms `:4700`, with `RZeroSorb` (`:4642-4658`) clearing the accumulators first.

---

## 1. The `SORPTION` block

Opened at `src/pflotran/reaction.F90:543` (pass 1) / `:1031` (pass 2). Sub-cards:

| Literal | Line | Handler |
|---|---|---|
| `SURFACE_COMPLEXATION_RXN` | `:639` | `ReactionSrfCplxReadSrfCplxRxn` (`reaction_surf_complex.F90:33`) |
| `ION_EXCHANGE_RXN` | `:641` | read inline, `:641-743` |
| `ISOTHERM_REACTIONS` | `:637` | `ReactionIsothermReadIsotherm` (`reaction_isotherm.F90:19`) |
| `DYNAMIC_KD_REACTIONS` | `:556` | read inline, `:556-636` |
| `JUMPSTART_KINETIC_SORPTION` | `:744` | sets `jumpstart_kinetic_sorption` **and** `no_restart_kinetic_sorption` (`:745-746`) |
| `NO_CHECKPOINT_KINETIC_SORPTION` | `:747` | checkpoint control |
| `NO_RESTART_KINETIC_SORPTION` | `:749` | restart control |

Unrecognized cards report the context string `'SORPTION'` (`:752`).

**Where sorbed mass enters the solve.** There is no explicit retardation factor in the residual. Equilibrium sorbed mass is added straight to the accumulation term, `RTAccumulation`, `src/pflotran/reaction.F90:5519-5524`:

```fortran
if (reaction%neqsorb > 0) then
  ! units = (mol solute/m^3 bulk)*(m^3 bulk)/(sec) = mol/sec
  Res(istart:iend) = Res(istart:iend) + &
    rt_auxvar%total_sorb_eq(:)*material_auxvar%volume
```

with the Jacobian counterpart at `:5611-5616`. A retardation number *is* computed, but only for output (`src/pflotran/reaction.F90:2675`).

Counts are aggregated at `src/pflotran/reaction.F90:910-916`: `neqsorb` = ion exchange + dynamic Kd + isotherms + equilibrium surface complexation; `nsorb` adds the multirate and kinetic surface-complexation reactions.

---

## 2. Surface complexation

Reader: `ReactionSrfCplxReadSrfCplxRxn`, `src/pflotran/reaction_surf_complex.F90:33`. The reaction type defaults to equilibrium at `:73` (`srfcplx_rxn%itype = SRFCMPLX_RXN_EQUILIBRIUM`); the sub-card `select case` is at `:87`.

| Literal | Line | Effect |
|---|---|---|
| `EQUILIBRIUM` | `:88` | equilibrium mass action |
| `MULTIRATE_KINETIC` | `:90` | multirate relaxation; also forces `reaction%equilibrate_at_each_cell = .true.` (`:94`) |
| `KINETIC` | `:95` | **fatal error at this commit** — `'Non-multirate kinetic surface complexation currently unsupported until implementation is fixed. Email pflotran-dev.'` (`:96-99`) |
| `COMPLEX_KINETICS` | `:101` | same fatal error (`:102-105`) |
| `RATE`, `RATES` | `:153` | array of rate constants; also sets `MULTIRATE_KINETIC` (`:154`) |
| `SITE_FRACTION` | `:158` | array of site fractions |
| `MULTIRATE_SCALE_FACTOR` | `:162` | multiplies every rate (`:306-307`) |
| `MINERAL` | `:166` | ties the surface to a named mineral (`surface_itype = MINERAL_SURFACE`) |
| `ROCK_DENSITY` | `:173` | `surface_itype = ROCK_SURFACE`; **takes no argument**, it only sets the flag |
| `SITE` | `:176` | free-site name + site density |
| `COMPLEXES` | `:185` | block listing the surface-complex names to include |

### 2.1 The `SITE` card and what its number actually means

`src/pflotran/reaction_surf_complex.F90:176-184`:

```fortran
case('SITE')
  call InputReadWord(input,option,srfcplx_rxn%free_site_name,PETSC_TRUE)
  ...
  ! site density in mol/m^3 bulk
  call InputReadDouble(input,option,srfcplx_rxn%site_density)
```

Two arguments: name, then density. **There is no units word and no unit conversion** anywhere in the `SITE` path — the number is copied through verbatim (`src/pflotran/reaction_database.F90:2956-2957`).

The comment says mol/m³ bulk, but the runtime meaning depends on the surface type (`src/pflotran/reaction_surf_complex.F90:697-711`):

```fortran
case(MINERAL_SURFACE)
  site_density(1) = surface_complexation%srfcplxrxn_site_density(irxn)* &
            rt_auxvar%mnrl_volfrac(surface_complexation%srfcplxrxn_to_surf(irxn))
case(ROCK_SURFACE)
  site_density(1) = surface_complexation%srfcplxrxn_site_density(irxn)* &
                    material_auxvar%soil_particle_density * &
                    (1.d0-material_auxvar%porosity)
case(NULL_SURFACE)
  site_density(1) = surface_complexation%srfcplxrxn_site_density(irxn)
```

So the deck number is:
- **mol per m³ mineral** when a `MINERAL` is named (multiplied by that mineral's volume fraction),
- **mol per kg solid** when `ROCK_DENSITY` is used (multiplied by soil particle density × solid fraction),
- **mol per m³ bulk** when neither.

This is a genuine trap: the same card means three different physical quantities. Note also the `MINERAL` coupling makes the site density track mineral dissolution automatically — relevant for a weathering column where sorption sites live on a dissolving phase.

### 2.2 Equilibrium mass action

`ReactionSrfCplxTotalSorbEq1`, `src/pflotran/reaction_surf_complex.F90:639`, mass action at `:743-762`:

$$S_i = \exp\Bigl[-\ln(10)\log K_i + \nu_{i,w}\ln a_{\mathrm{H_2O}} + \nu_{i,x}\ln S_x + \sum_j \nu_{ij}\ln a_j\Bigr]$$

where $S_x$ is the free-site concentration and $\nu_{i,x}$ the free-site stoichiometry read from the database record (`src/pflotran/reaction_database.F90:413-416`, the species whose name starts with `>`).

The site balance closes the system (`:738`, `:761-762`):

$$S_x + \sum_i \nu_{i,x} S_i = \Gamma_{\mathrm{site}}$$

Two solution branches at `:768`. If every free-site stoichiometry is 1, `S_x` is obtained directly (`:797-798`). Otherwise a Newton iteration runs with `tol = 1.d-12` (`:675`), residual `res = site_density(isite)-total` (`:771`), and 0.5 damping after 1000 iterations (`:785-787`). Derivatives at `:813-839`, accumulation into `total_sorb` at `:865-866`.

**No electrostatic / diffuse-double-layer term appears in the mass action.** The only double-layer code in the tree is output-only and behind a compile flag: `src/pflotran/reaction.F90:2635` `#ifdef DOUBLE_LAYER` → `ReactionDoubleLayer` (`:2860-3050`), enabled by `make dbl=1` (`src/pflotran/makefile:94-96`). **There is no `DOUBLE_LAYER` or `ELECTROSTATIC` input-deck keyword at this commit.** Practical consequence: PFLOTRAN's surface complexation here is a non-electrostatic (constant-capacitance-free) model. Do not attempt to reproduce a triple-layer or diffuse-layer model result with it.

### 2.3 Multirate kinetic surface complexation

`ReactionSrfCplxMultirateRate`, `src/pflotran/reaction_surf_complex.F90:550`. It first computes the equilibrium target (`:602-607`) and then relaxes toward it in each rate class (`:610-625`):

```fortran
do irate = 1, surface_complexation%kinmr_nrate(ikinmrrxn)
  kdt = surface_complexation%kinmr_rate(irate,ikinmrrxn) * option%tran_dt
  one_plus_kdt = 1.d0 + kdt
  k_over_one_plus_kdt = surface_complexation%kinmr_rate(irate,ikinmrrxn)/one_plus_kdt

  Res(:) = Res(:) + material_auxvar%volume * k_over_one_plus_kdt * &
    (surface_complexation%kinmr_frac(irate,ikinmrrxn)*total_sorb_eq(:) - &
     rt_auxvar%kinmr_total_sorb(:,irate,ikinmrrxn))
```

i.e. a backward-Euler-linearized first-order relaxation

$$R_j = V\,\frac{k_j}{1+k_j\Delta t}\bigl(f_j S^{\mathrm{eq}} - S_j\bigr)$$

**Rate units are not stated anywhere in source** — no units word, no conversion, no comment on `kinmr_rate` (declared bare at `src/pflotran/reaction_surf_complex_aux.F90:125`). Dimensionally they must be s⁻¹ because `kdt = rate * option%tran_dt` (`:611-612`). Treat that as an inference, not a documented contract.

If `SITE_FRACTION` is omitted, uniform fractions are generated (`:288-290`); the `RATES` and `SITE_FRACTION` arrays must be the same length (`:294-302`) and the fractions must sum to 1 within `1.d-6` (`:310-316`). There is a caveat comment on the formulation itself at `:609`: `! WARNING: this assumes site fraction multiplicative factor`.

State update at end of step: `ReactionSrfCplxMRUpdateKinState` (`:1106`), called from `RUpdateKineticState` (`src/pflotran/reaction.F90:5745`).

The non-multirate kinetic path, `ReactionSrfCplxKineticRate` (`:902`), is unreachable at this commit because its keyword errors out; it does carry an explicit units block at `:951-954` (`k_f` in dm³/mol/s, `k_b` in 1/s).

---

## 3. Isotherms

Reader: `ReactionIsothermReadIsotherm`, `src/pflotran/reaction_isotherm.F90:19`. Each sub-block is opened by a **species name** (`:68`). The type is reset to `SORPTION_LINEAR` on every card (`:92`), before the `select case`.

| Literal | Line | Effect |
|---|---|---|
| `TYPE` → `LINEAR` | `:98` | `SORPTION_LINEAR` |
| `TYPE` → `LANGMUIR` | `:100` | `SORPTION_LANGMUIR` |
| `TYPE` → `FREUNDLICH` | `:102` | `SORPTION_FREUNDLICH` |
| `DISTRIBUTION_COEFFICIENT` | `:114` | `Kd`, with an optional units word (`:117-118`) |
| `KD` | `:111` | **deprecated** → `DISTRIBUTION_COEFFICIENT` (`:112-113`) |
| `LANGMUIR_B` | `:131` | `Langmuir_B`; also forces the type to Langmuir (`:134`) |
| `FREUNDLICH_N` | `:135` | `Freundlich_N`; also forces the type to Freundlich (`:138`) |
| `KD_MINERAL_NAME` | `:139` | scale Kd by a mineral's volume fraction |
| `SEC_CONT_DISTRIBUTION_COEFFICIENT`, `SEC_CONT_KD` | `:120-121` | secondary-continuum Kd |

Type constants at `src/pflotran/pflotran_constants.F90:141-143`.

### 3.1 Kd units

`ReactionIsothermConvertKDUnits`, `src/pflotran/reaction_isotherm.F90:222`. Two internal systems (`src/pflotran/reaction_isotherm_aux.F90:12-13`): `KD_UNIT_KG_M3_BULK = 0` and `KD_UNIT_MLW_GSOIL = 1`. The converter tries `kg/m^3` first (`:245-246`) and falls back to `L/kg` (`:249-250`). Units must be consistent across the entire deck (`:173-189`).

Normalization at evaluation time (`src/pflotran/reaction_isotherm.F90:306-317`):

```fortran
if (isotherm%ikd_units == KD_UNIT_MLW_GSOIL) then
               !KD units [mL water/g soil]
  kd_kgw_m3b = isotherm_rxn%eqisothermcoeff(irxn) * &
               global_auxvar%den_kg(iphase) * &
               (1.d0-material_auxvar%porosity) * &
               material_auxvar%soil_particle_density * &
               1.d-3 ! convert mL water/g soil to m^3 water/kg soil
```

A mass-basis Kd therefore depends on porosity and `soil_particle_density` — those must be set in `MATERIAL_PROPERTY` or the sorption is silently wrong. `KD_MINERAL_NAME` applies a further multiplication by the mineral's volume fraction, with an explicit disclaimer in source (`:319-321`): *"NOTE: mineral volume fraction here is solely a scaling factor. It has nothing to do with the soil volume."*

### 3.2 The three isotherms as coded

`src/pflotran/reaction_isotherm.F90:325-346`, all in terms of molality $m$ and the normalized coefficient $K$ (`kd_kgw_m3b`):

| Type | Equation (source comment + code) | Parameters |
|---|---|---|
| `LINEAR` | `Csorb = Kd*Caq` → $S = K m$ (`:328`) | `DISTRIBUTION_COEFFICIENT` |
| `LANGMUIR` | `Csorb = K*Caq*b/(1+K*Caq)` → $S = \dfrac{K m\, b}{1 + K m}$ (`:333-335`) | `DISTRIBUTION_COEFFICIENT` ($K$), `LANGMUIR_B` ($b$, the sorption maximum) |
| `FREUNDLICH` | `Csorb = Kd*Caq**(1/n)` → $S = K m^{1/n}$ (`:341`) | `DISTRIBUTION_COEFFICIENT`, `FREUNDLICH_N` ($n$; note the code uses $1/n$) |

Accumulated into `total_sorb_eq` / `dtotal_sorb_eq` at `:347-349`. Sorbed concentration $S$ is in mol per m³ bulk.

Cosmetic note: `molality_one_over_n` is computed at `:340` and then not used at `:341` (the expression is recomputed inline). Harmless.

---

## 4. Ion exchange

Parsed inline at `src/pflotran/reaction.F90:641-743`; set up at `src/pflotran/reaction_database.F90:3020-3075`; evaluated in `RTotalSorbEqIonx` (`src/pflotran/reaction.F90:4779-5004`).

| Literal | Line | Meaning |
|---|---|---|
| `MINERAL` | `:655` | ties the exchange capacity to a kinetic mineral's volume fraction |
| `CEC` | `:659` | cation exchange capacity |
| `CATIONS` | `:662` | block of `<cation_name> <k> [REFERENCE]` rows |
| `REFERENCE` | `:681` | marks the reference cation on its row |

**`CATION_EXCHANGE_CAPACITY` and `SELECTIVITY` do NOT exist at this commit.** The card is spelled `CEC`, and the selectivity coefficient is the *unlabelled second column* of each `CATIONS` row (read at `:676`).

Rules enforced: exactly one cation must be marked `REFERENCE` (`:697-701`), and it must have $k = 1$ (`:707-711`). The reference cation is then moved to the head of the list (`:713-718`). `CEC` is mandatory (`src/pflotran/reaction_database.F90:3037-3041`).

Exchange capacity at runtime (`src/pflotran/reaction.F90:4823-4831`):

```fortran
! for now we assume that omega is equal to CEC.
if (reaction%eqionx_rxn_to_surf(irxn) > 0) then
  omega = max(reaction%eqionx_rxn_CEC(irxn)* &
              rt_auxvar%mnrl_volfrac(reaction%eqionx_rxn_to_surf(irxn)),1.d-40)
else
  omega = reaction%eqionx_rxn_CEC(irxn)
endif
```

**Convention.** The source never names a convention — `grep -rni "gaines\|vanselow\|gapon" src/pflotran/*.F90` returns nothing in any reaction file. It must be inferred. The unequal-charge branch (`:4833` onward) solves for a variable `KDj` such that charge-weighted equivalent fractions sum to one, `res = 1.d0 - total` (`:4871`), with

```fortran
cation_X(j) = reaction%eqionx_rxn_k(j,irxn)* &
              rt_auxvar%pri_molal(icomp)* &
              rt_auxvar%pri_act_coef(icomp)* &
              KDj**(reaction%primary_spec_Z(icomp)/ref_cation_Z)
```
(`:4860-4864`), and converts equivalent fraction to moles by dividing by charge (`:4964`):
```fortran
tempreal1 = cation_X(i)*omega/reaction%primary_spec_Z(icomp)
```

That is the **Gaines-Thomas** (equivalent-fraction) convention, but the code does not say so and no reference is cited. Treat this as a strong inference, not a documented fact. Iteration cap is 20000 (`:4846-4850`). The equal-charge branch (`:4946-4961`) is a simple normalized $k_i a_i / \sum_j k_j a_j$.

Output units are confirmed by the print format at `src/pflotran/reaction.F90:2665-2666`: sorbed concentration in mol/m³.

---

## 5. Dynamic Kd

Parsed inline at `src/pflotran/reaction.F90:556-636`. Required sub-cards, all fatal if missing (`:614-623`): `REFERENCE_SPECIES` (`:584`), `REFERENCE_SPECIES_HIGH` (`:589`), `KD_LOW` (`:595`), `KD_HIGH` (`:599`), `KD_POWER` (`:603`). Evaluated in `RTotalSorbDynamicKD` (`src/pflotran/reaction.F90:4709-4775`). This makes Kd a power-law function of a reference species' concentration between a low and high anchor.

---

## 6. Calibration knobs summary

| Deck keyword | Source line | Units | Default | Physically controls |
|---|---|---|---|---|
| `SITE <name> <density>` | `reaction_surf_complex.F90:176` | mol/m³ mineral, mol/kg solid, or mol/m³ bulk — depends on `MINERAL`/`ROCK_DENSITY` (`:697-711`) | required | total sorption site inventory; the dominant surface-complexation knob |
| database surface-complex `logK` | `reaction_database.F90:423` | log₁₀ | from file | binding strength of each surface complex |
| `MINERAL <name>` | `reaction_surf_complex.F90:166` | name | none | makes site density track that mineral's volume fraction |
| `ROCK_DENSITY` | `reaction_surf_complex.F90:173` | flag (no argument) | none | reinterprets site density as mol/kg solid |
| `RATES` | `reaction_surf_complex.F90:153` | s⁻¹ (inferred, undocumented) | none | multirate relaxation timescales |
| `SITE_FRACTION` | `reaction_surf_complex.F90:158` | dimensionless, must sum to 1 | uniform (`:288-290`) | how sites are partitioned across rate classes |
| `MULTIRATE_SCALE_FACTOR` | `reaction_surf_complex.F90:162` | dimensionless | 1 | uniform multiplier on all rates |
| `DISTRIBUTION_COEFFICIENT` | `reaction_isotherm.F90:114` | `kg/m^3` (bulk basis) or `L/kg` / mL·g⁻¹ (mass basis) | required | linear/Langmuir/Freundlich sorption strength |
| `LANGMUIR_B` | `reaction_isotherm.F90:131` | mol/m³ bulk | required for Langmuir | sorption maximum |
| `FREUNDLICH_N` | `reaction_isotherm.F90:135` | dimensionless | required for Freundlich | isotherm nonlinearity ($m^{1/n}$) |
| `KD_MINERAL_NAME` | `reaction_isotherm.F90:139` | name | none | scales Kd by a mineral volume fraction |
| `CEC` | `reaction.F90:659` | mol/m³ bulk (or per m³ mineral if `MINERAL` given) | required | exchange capacity |
| `CATIONS` column 2 | `reaction.F90:676` | dimensionless | reference must be 1 | selectivity coefficients |
| `KD_LOW` / `KD_HIGH` / `KD_POWER` | `reaction.F90:595`/`:599`/`:603` | Kd units / dimensionless | required | dynamic-Kd envelope and curvature |
| `soil_particle_density`, `POROSITY` (MATERIAL_PROPERTY) | consumed at `reaction_isotherm.F90:309-311`, `reaction_surf_complex.F90:705-706` | kg/m³, m³/m³ | — | silently rescales every mass-basis Kd and every `ROCK_DENSITY` site density |

## 7. Things I could not verify

- The units of `RATES` under `MULTIRATE_KINETIC`. The source contains no units string, no conversion, and no comment; s⁻¹ is a dimensional inference from `kdt = rate * option%tran_dt` (`reaction_surf_complex.F90:611-612`).
- The ion-exchange convention. The equations are consistent with Gaines-Thomas, but the source names no convention and cites no reference.
- The meaning of the `WARNING: this assumes site fraction multiplicative factor` comment at `reaction_surf_complex.F90:609` — what breaks if the assumption fails is not stated.
- Whether `SRFCMPLX_RXN_KINETIC` post-processing at `reaction_surf_complex.F90:317` is dead code given that its keyword errors out at `:95`.
