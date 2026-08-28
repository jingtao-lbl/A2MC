**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** Mineral precipitation/dissolution kinetics (transition-state theory)
**Last verified:** 2026-07-31

# Mineral Kinetics

Owning files: `src/pflotran/reaction_mineral.F90` (2208 lines), `src/pflotran/reaction_mineral_aux.F90` (1032 lines). Parameters are transferred from the linked-list parse structures into flat arrays in `src/pflotran/reaction_database.F90` (`ReactionDBInitBasis`, the block at lines 1959–2580). Constraint (initial-condition) parsing lives in `src/pflotran/transport_constraint_rt.F90`.

This is the highest-value topic for a basalt-weathering column: every knob below multiplies directly into the dissolution rate.

---

## 1. The rate law as implemented

There are **two** rate routines. PFLOTRAN picks one per mineral at setup time.

| Routine | Line | Selected when |
|---|---|---|
| `ReactionMnrlKineticRateTSTSimple` | `src/pflotran/reaction_mineral.F90:1201` | no activation energy, no prefactor, no Temkin constant, no mineral scale factor, no affinity threshold, no rate limiter |
| `ReactionMnrlKineticRateTST` | `src/pflotran/reaction_mineral.F90:1329` | any one of the above is set |

The selection logic is `src/pflotran/reaction_database.F90:2520-2566`; it sets `kinmnrl_tst_itype` to `MINERAL_KINETICS_TST_SIMPLE` or `MINERAL_KINETICS_TST_COMPLEX` (parameters defined at `src/pflotran/reaction_mineral_aux.F90:18-19`). The dispatch is `src/pflotran/reaction_mineral.F90:1173-1186`.

**Warning for calibration.** The `found` flag at `src/pflotran/reaction_database.F90:2520-2560` is raised by activation energy, prefactors, Temkin constant, mineral scale factor, affinity threshold, and rate limiter — **`AFFINITY_POWER` is not among them.** A mineral whose only extra card is `AFFINITY_POWER` is therefore routed to the **SIMPLE** routine, and the SIMPLE routine has no exponent on the affinity factor at all (`src/pflotran/reaction_mineral.F90:1281`: `Im = Im_const*sign_*dabs(affinity_factor)*rate_constant`). The `AFFINITY_POWER` value is silently ignored.

A reliable way to force the COMPLEX path is to add `ACTIVATION_ENERGY 0.d0`: the sentinel is `UNINITIALIZED_DOUBLE = -999.d0` (`src/pflotran/pflotran_constants.F90:300`), so an explicit `0.d0` counts as `Initialized` and raises `found` (`src/pflotran/reaction_database.F90:2468-2471`, `:2524-2528`), while the Arrhenius factor stays exactly 1 because it is applied only when the activation energy is strictly positive (`src/pflotran/reaction_mineral.F90:1488`). Verify against a printed mineral rate before trusting any `AFFINITY_POWER` calibration.

### 1.1 Ion activity product / saturation ratio

Both routines start identically (`src/pflotran/reaction_mineral.F90:1244-1257` simple, `1392-1405` complex):

```fortran
lnQK = -mineral%kinmnrl_logK(imnrl)*LOG_TO_LN
if (mineral%kinmnrlh2oid(imnrl) > 0) then
  lnQK = lnQK + mineral%kinmnrlh2ostoich(imnrl)*rt_auxvar%ln_act_h2o
endif
do i = 1, mineral%kinmnrlspecid(0,imnrl)
  icomp = mineral%kinmnrlspecid(i,imnrl)
  lnQK = lnQK + mineral%kinmnrlstoich(i,imnrl)*ln_act(icomp)
enddo
QK = exp(lnQK)
```

So the code's `QK` is the **saturation ratio** $Q/K$:

$$\frac{Q}{K} \;=\; \frac{a_{\mathrm{H_2O}}^{\nu_w}\prod_j a_j^{\nu_j}}{10^{\log K}}$$

with $\nu_j$ the stoichiometric coefficients of the mineral **dissolution** reaction as written in the database, and $a_j = m_j\gamma_j$ (`ln_act = ln_conc + log(pri_act_coef)`, `src/pflotran/reaction_mineral.F90:1165`). `LOG_TO_LN = 2.30258509299d0` (`src/pflotran/pflotran_constants.F90:86`).

Note `ln_act(icomp)` uses only **primary** species activities. Secondary complexes enter $Q/K$ only through their effect on the primary speciation, not directly.

### 1.2 The affinity factor

Simple path (`src/pflotran/reaction_mineral.F90:1259`):

$$f_{\mathrm{aff}} = 1 - Q/K$$

Complex path (`src/pflotran/reaction_mineral.F90:1407-1421`), with the Temkin constant $\sigma$ and the mineral scale factor $s$:

$$f_{\mathrm{aff}} = 1 - \left(\frac{Q}{K}\right)^{1/(s\,\sigma)}$$

where $\sigma$ is present only if `TEMKIN_CONSTANT` was given for some mineral and $s$ only if `MINERAL_SCALE_FACTOR` was; each defaults to 1 when its array exists but the entry is unset (`src/pflotran/reaction_database.F90:2536`, `2544`). If neither array exists the plain $1 - Q/K$ form is used (`:1420`).

$f_{\mathrm{aff}} > 0 \Rightarrow$ undersaturated $\Rightarrow$ **dissolution**; $f_{\mathrm{aff}} < 0 \Rightarrow$ **precipitation** (`sign_` at `src/pflotran/reaction_mineral.F90:1261` / `:1423`, comment: `sign_ > 0 = dissolution`).

### 1.3 Full rate expression (complex path)

`src/pflotran/reaction_mineral.F90:1506-1520`:

```fortran
Im_const = -rt_auxvar%mnrl_area(imnrl)
if (associated(mineral%kinmnrl_mnrl_scale_factor)) then
  Im_const = Im_const/mineral%kinmnrl_mnrl_scale_factor(imnrl)
endif
...
Im = Im_const*sign_* &
      dabs(affinity_factor)**mineral%kinmnrl_affinity_power(imnrl)* &
      sum_prefactor_rate
```

Written out, the volumetric rate $I_m$ [mol m⁻³ bulk s⁻¹] is

$$I_m \;=\; -\,\frac{A_m}{s}\;\operatorname{sgn}(f_{\mathrm{aff}})\;\bigl|f_{\mathrm{aff}}\bigr|^{\beta}\;\sum_{p} P_p \, k_p \, \exp\!\left[\frac{E_{a,p}}{R}\left(\frac{1}{T_{\mathrm{ref}}}-\frac{1}{T}\right)\right]$$

| Symbol | Code variable | Deck keyword | Units |
|---|---|---|---|
| $A_m$ | `rt_auxvar%mnrl_area(imnrl)` | `CONSTRAINT/MINERALS` col. 3 + `SURFACE_AREA_FUNCTION` | m² mineral / m³ bulk |
| $s$ | `kinmnrl_mnrl_scale_factor` | `MINERAL_SCALE_FACTOR` | dimensionless |
| $f_{\mathrm{aff}}$ | `affinity_factor` | (derived) | dimensionless |
| $\beta$ | `kinmnrl_affinity_power` | `AFFINITY_POWER` | dimensionless |
| $\sigma$ | `kinmnrl_Temkin_const` | `TEMKIN_CONSTANT` | dimensionless |
| $k_p$ | `kinmnrl_pref_{precip,dissol}_rate_const` or `kinmnrl_{precip,dissol}_rate_constant` | `RATE_CONSTANT` / `PRECIPITATION_RATE_CONSTANT` / `DISSOLUTION_RATE_CONSTANT` | mol m⁻² s⁻¹ |
| $E_{a,p}$ | `kinmnrl_{pref_}activation_energy` | `ACTIVATION_ENERGY` | J mol⁻¹ |
| $P_p$ | `prefactor(ipref)` | `PREFACTOR` / `PREFACTOR_SPECIES` | dimensionless |

$T_{\mathrm{ref}} = 25\,^\circ$C, hard-coded as `PetscReal, parameter :: TREF = 25.d0` (`src/pflotran/reaction_mineral.F90:1383`). The Arrhenius factor is `Utility_module::Arrhenius` (`src/pflotran/utility.F90:2885-2910`):

```fortran
Arrhenius = exp(activation_energy / IDEAL_GAS_CONSTANT * &
                (1.d0/(reference_temperature + T273K) - &
                 1.d0/(temperature + T273K)))
```

with `IDEAL_GAS_CONSTANT = 8.31446d0` J mol⁻¹ K⁻¹ (`src/pflotran/pflotran_constants.F90:91`) and `T273K = 273.15d0` (`:93`). Temperatures are supplied in °C. The Arrhenius factor is applied **only if the activation energy is strictly positive** (`src/pflotran/reaction_mineral.F90:1473`, `:1488`); otherwise the factor is exactly 1.

**Sign convention:** `Im_const` is negative (`-mnrl_area`), so for dissolution (`sign_ > 0`) the stored `mnrl_rate` is **negative**. That negative rate shrinks the volume fraction at `src/pflotran/reaction_mineral.F90:2168-2172`:

```fortran
delta_volfrac = rt_auxvar%mnrl_rate(imnrl)* &
                reaction%mineral%kinmnrl_molar_vol(imnrl)* &
                option%tran_dt
rt_auxvar%mnrl_volfrac(imnrl) = rt_auxvar%mnrl_volfrac(imnrl) + delta_volfrac
```

Volume fraction is clipped at zero (`:2173-2174`). **Negative `mnrl_rate` output = dissolution.**

### 1.4 The prefactor (parallel rate laws)

Each `PREFACTOR` block is one parallel pathway (e.g. an acid mechanism, a neutral mechanism). Within a pathway, each `PREFACTOR_SPECIES` contributes a Monod-like factor (`src/pflotran/reaction_mineral.F90:1451-1471`):

$$P_p = \prod_{j} \frac{a_j^{\alpha_j}}{1 + c_j\,a_j^{\beta_j}}$$

with `ALPHA` $=\alpha_j$, `BETA` $=\beta_j$, `ATTENUATION_COEF` $=c_j$ (parsed at `src/pflotran/reaction_mineral.F90:279-290`, defaults all `0.d0` at `src/pflotran/reaction_mineral_aux.F90:435-437`). With only `ALPHA` set, this reduces to the classical $a_{\mathrm{H^+}}^{n}$ pH dependence.

Prefactor species may be **primary or secondary**; secondary species are stored with a negated id (`src/pflotran/reaction_database.F90:2390-2397`, used at `src/pflotran/reaction_mineral.F90:1453-1457`).

Hard limits: at most **10 prefactors** and **5 species per prefactor** — the local arrays are fixed size, `PetscReal :: prefactor(10), ln_prefactor_spec(5,10)` (`src/pflotran/reaction_mineral.F90:1374`, comment at `:1365`).

A prefactor that omits `RATE_CONSTANT` or `ACTIVATION_ENERGY` inherits the outer-block value (`src/pflotran/reaction_mineral.F90:443-471`); if both are missing PFLOTRAN errors out (`:450-455`).

---

## 2. Deck keywords: `CHEMISTRY / MINERAL_KINETICS / <mineral>`

Parsed in `ReactionMnrlReadKinetics`, `src/pflotran/reaction_mineral.F90:84-529`. The mineral name must already appear in the `CHEMISTRY / MINERALS` list (`ReactionMnrlRead`, `src/pflotran/reaction_mineral.F90:35-80`); otherwise it is a fatal error (`:497-501`).

| Keyword | Parse line | Field set | Units | Default |
|---|---|---|---|---|
| `RATE_CONSTANT` | `:159`,`:166` | both `precipitation_rate_constant` and `dissolution_rate_constant` | mol m⁻² s⁻¹ | none — required (`:472-477`) |
| `PRECIPITATION_RATE_CONSTANT` | `:159`,`:169` | `precipitation_rate_constant` | mol m⁻² s⁻¹ | uninitialized |
| `DISSOLUTION_RATE_CONSTANT` | `:159`,`:171` | `dissolution_rate_constant` | mol m⁻² s⁻¹ | uninitialized |
| `ACTIVATION_ENERGY` | `:174` | `activation_energy` | J mol⁻¹ (converted, `:178-180`) | 0 (`reaction_database.F90:2525`) |
| `AFFINITY_THRESHOLD` | `:181` | `affinity_threshold` | dimensionless ($Q/K$) | 0 (`reaction_database.F90:2551`) |
| `AFFINITY_POWER` | `:185` | `affinity_factor_beta` | dimensionless | 1 (`reaction_database.F90:2073`) |
| `MINERAL_SCALE_FACTOR` | `:189` | `mnrl_scale_factor` | dimensionless | 1 (`reaction_database.F90:2544`) |
| `TEMKIN_CONSTANT` | `:193` | `affinity_factor_sigma` | dimensionless | 1 (`reaction_database.F90:2536`) |
| `SURFACE_AREA_POROSITY_POWER` | `:197` | `surf_area_porosity_pwr` | dimensionless | uninitialized (required by some `SURFACE_AREA_FUNCTION`s) |
| `SURFACE_AREA_VOL_FRAC_POWER` | `:200` | `surf_area_vol_frac_pwr` | dimensionless | uninitialized |
| `RATE_LIMITER` | `:203` | `rate_limiter` | dimensionless | 0 = off (`reaction_database.F90:2557`) |
| `ARMOR_MINERAL` | `:207` | `armor_min_name` | mineral name | `''` |
| `ARMOR_PWR` | `:211` | `armor_pwr` | dimensionless | 0 |
| `ARMOR_CRIT_VOL_FRAC` | `:215` | `armor_crit_vol_frac` | m³/m³ | 0 |
| `SPECIFIC_SURFACE_AREA_EPSILON` | `:218` | `surf_area_epsilon` | m² m⁻³ bulk | 0 |
| `VOLUME_FRACTION_EPSILON` | `:221` | `vol_frac_epsilon` | m³ m⁻³ | 0 |
| `PREFACTOR` (block) | `:224` | prefactor list | — | none |
| `SURFACE_AREA_FUNCTION` | `:331` | `surf_area_function` | enum | `CONSTANT` (`reaction_mineral_aux.F90:374`) |
| `SPECIFIC_SURFACE_AREA` | `:353` | `spec_surf_area` | m²/kg (converted, `:356-357`) | uninitialized |
| `NUCLEATION_KINETICS` | `:358` | `nucleation` | name of a `NUCLEATION` block | none |

Inside a `PREFACTOR` block the accepted keywords are `RATE_CONSTANT` / `PRECIPITATION_RATE_CONSTANT` / `DISSOLUTION_RATE_CONSTANT` (`:239`), `ACTIVATION_ENERGY` (`:256`), `PREFACTOR_SPECIES` (`:264`). Inside `PREFACTOR_SPECIES`: `ALPHA` (`:279`), `BETA` (`:283`), `ATTENUATION_COEF` (`:287`).

### 2.1 The negative-`RATE_CONSTANT` reinterpretation — CONFIRMED

`ReactionMnrlReadRateConstant`, `src/pflotran/reaction_mineral.F90:533-580`:

```fortran
call InputReadDouble(input,option,rate_constant)
if (rate_constant < 0.d0) then
  rate_constant = 10.d0**rate_constant
endif
```
(`src/pflotran/reaction_mineral.F90:561-564`)

A **negative** value is interpreted as $\log_{10} k$. `RATE_CONSTANT -10.0` means $k = 10^{-10}$ mol m⁻² s⁻¹, not $-10$. Consequences for a calibration agent:

- The transformation is applied **before** unit conversion (`:574-577`), so `RATE_CONSTANT -10.0 mol/cm^2-sec` is $10^{-10}$ mol cm⁻² s⁻¹ then converted.
- There is **no way to express a rate constant between −1 and 0**, and no way to express a negative rate. The parameter is effectively piecewise: $k \in (0,\infty)$ for positive input, $k = 10^{x}$ for $x<0$.
- **A Morris/Sobol sampler must not sample `RATE_CONSTANT` across zero.** Sample $\log_{10}k$ and write the negative value, or sample $k>0$ directly. Mixing the two branches inside one parameter range produces a discontinuous, non-monotone map.
- `rate_constant = 0.d0` is legal input and short-circuits the reaction: `if (.not.(rate_constant > 0.d0)) return` (`:1272`, and `:1500` for the summed prefactor rate).

Default internal units are `mol/m^2-sec` (`src/pflotran/reaction_mineral.F90:567`); an optional units word may follow the number (`:568-578`).

### 2.2 `AFFINITY_THRESHOLD` and `RATE_LIMITER`

Both act only on **precipitation** and only in the complex routine.

`AFFINITY_THRESHOLD` (`src/pflotran/reaction_mineral.F90:1431-1434`):

```fortran
if (mineral%kinmnrl_affinity_threshold(imnrl) > 0.d0) then
  if (precipitation .and. &
      QK < mineral%kinmnrl_affinity_threshold(imnrl)) return
endif
```

Precipitation is suppressed entirely until $Q/K$ exceeds the threshold — a supersaturation (nucleation-barrier) cutoff. Since precipitation already requires $Q/K > 1$, useful values are $>1$. Units: dimensionless saturation ratio, **not** a saturation index in log units.

`RATE_LIMITER` $r$ (`src/pflotran/reaction_mineral.F90:1437-1440`):

```fortran
affinity_factor = affinity_factor/(1.d0+(1.d0-affinity_factor) &
  /mineral%kinmnrl_rate_limiter(imnrl))
```

i.e. $f_{\mathrm{aff}} \leftarrow f_{\mathrm{aff}} / \bigl(1 + (Q/K)/r\bigr)$ (using $1-f_{\mathrm{aff}} = (Q/K)^{1/(s\sigma)}$). As $Q/K \to \infty$ the limited factor asymptotes to $-r$, capping the precipitation rate at $A_m k r / s$. Dissolution ($Q/K \to 0$) is essentially unaffected. Setting `RATE_LIMITER` is checked against `AFFINITY_POWER`: the combination is a fatal error unless every mineral's affinity power is 1 (`src/pflotran/reaction_database.F90:2569-2580`).

### 2.3 Consistency checks enforced at parse time

- Specifying only one of `PRECIPITATION_RATE_CONSTANT` / `DISSOLUTION_RATE_CONSTANT` is fatal — both must be set if either is (`src/pflotran/reaction_mineral.F90:368-376`).
- `SURFACE_AREA_POROSITY_POWER` requires a `SURFACE_AREA_FUNCTION` of `POROSITY_RATIO` or `POROSITY_VOLUME_FRACTION_RATIO`; `MINERAL_MASS` is explicitly rejected (`:378-393`). Symmetric check for `SURFACE_AREA_VOL_FRAC_POWER` (`:394-409`).
- Conversely each ratio-based `SURFACE_AREA_FUNCTION` requires its power(s), and `MINERAL_MASS` requires `SPECIFIC_SURFACE_AREA` (`:410-440`).
- A kinetic mineral with no rate constant and no prefactor is fatal (`:472-477`).

---

## 3. Specific surface area and its evolution

`ReactionMnrlUpdateSpecSurfArea`, `src/pflotran/reaction_mineral.F90:1999-2120`. It is called per grid cell from `src/pflotran/realization_subsurface.F90:2004`, guarded by `reaction%mineral%update_surface_area` (`:1994`), which is set the moment any `SURFACE_AREA_FUNCTION` card is read (`src/pflotran/reaction_mineral.F90:332`).

### 3.1 Ratio-based functions

For `POROSITY_RATIO`, `VOLUME_FRACTION_RATIO`, `POROSITY_VOLUME_FRACTION_RATIO` (`src/pflotran/reaction_mineral.F90:2035-2071`):

$$A_m \;=\; \max\!\bigl(A_m^0,\;\epsilon_A\bigr)\;\underbrace{\left(\frac{1-\phi}{1-\phi_0}\right)^{p}}_{\texttt{porosity\_scale}}\;\underbrace{\left(\frac{\varphi_m}{\varphi_m^0}\right)^{q}}_{\texttt{volfrac\_scale}}$$

```fortran
porosity_scale = &
    ((1.d0-material_auxvar%porosity_base) / &
    (1.d0-porosity0))** &
    mineral%kinmnrl_surf_area_porosity_pwr(imnrl)
...
volfrac_scale = (mnrl_volfrac/mnrl_volfrac0)** &
                mineral%kinmnrl_surf_area_vol_frac_pwr(imnrl)
...
rt_auxvar%mnrl_area(imnrl) = &
    max(rt_auxvar%mnrl_area0(imnrl), &
        mineral%kinmnrl_surf_area_epsilon(imnrl)) * &
    porosity_scale*volfrac_scale
```
(`src/pflotran/reaction_mineral.F90:2052-2071`)

**Surprise worth flagging:** despite the keyword name `POROSITY_RATIO`, the ratio taken is of the **solid fraction** $(1-\phi)/(1-\phi_0)$, not $\phi/\phi_0$. A modeler porting a rate law from a paper that uses $\phi/\phi_0$ will get the wrong sign of response. The exponent is `SURFACE_AREA_POROSITY_POWER` ($p$); the volume-fraction exponent is `SURFACE_AREA_VOL_FRAC_POWER` ($q$). `POROSITY_RATIO` forces `volfrac_scale = 1` (`:2042`), `VOLUME_FRACTION_RATIO` forces `porosity_scale = 1` (`:2046`).

Both $\varphi_m$ and $\varphi_m^0$ are floored at `VOLUME_FRACTION_EPSILON` before the ratio (`:2058-2061`) — this is the guard that prevents a mineral that has dissolved to zero from permanently losing all reactive surface (with $\epsilon_\varphi = 0$ and $\varphi_m = 0$, `volfrac_scale` is 0 and the mineral can never re-precipitate on itself). Set `VOLUME_FRACTION_EPSILON` to a small positive number if a secondary phase must be able to nucleate. `SPECIFIC_SURFACE_AREA_EPSILON` ($\epsilon_A$) plays the same role for the base area.

$\phi_0$ is the cell's initial porosity, read from the PETSc `Vec` `field%porosity0` (`src/pflotran/realization_subsurface.F90:1996`, `:2002`); $\phi$ is `material_auxvar%porosity_base`. $A_m^0$ and $\varphi_m^0$ come from the constraint (§3.3).

### 3.2 `MINERAL_MASS`

`src/pflotran/reaction_mineral.F90:2106-2115`, with the unit derivation in the source comment:

$$A_m \;=\; S_m \cdot \frac{W_m}{V_m} \cdot \varphi_m$$

```fortran
! m^2 mnrl/m^3 bulk = m^2 mnrl/kg mnrl *    [specific surface area]
!                     kg mnrl/mol mnrl /    [formula weight]
!                     m^3 mnrl/mol mnrl *   [molar volume]
!                     m^3 mnrl/m^3 bulk     [volume fraction]
rt_auxvar%mnrl_area(imnrl) = &
  mineral%kinmnrl_spec_surf_area(imnrl) * &
  mineral%kinmnrl_molar_wt(imnrl) / &
  mineral%kinmnrl_molar_vol(imnrl) * &
  rt_auxvar%mnrl_volfrac(imnrl)
```

$S_m$ = `SPECIFIC_SURFACE_AREA` [m²/kg], $W_m$ = molar weight [kg/mol] and $V_m$ = molar volume [m³/mol], both read from the database. This form is linear in volume fraction and ignores the constraint's area column entirely, which makes it the cleanest choice when a BET measurement is available. Note it also ignores `mnrl_area0`, so a mineral at zero volume fraction has zero area and cannot precipitate.

`CONSTANT` (`MINERAL_SURF_AREA_F_NULL`) falls to `case default` (`:2116`) and leaves `mnrl_area` at its constraint value forever.

### 3.3 Where $A_m^0$ and $\varphi_m^0$ come from

`CONSTRAINT / MINERALS` rows are `<mineral_name> <volume_fraction> <specific_surface_area> [units]`, parsed at `src/pflotran/transport_constraint_rt.F90:509-558`. The units word defaults to `m^2/m^3` (`:554`). **Every kinetic mineral must appear**, even at zero volume fraction — a shorter list is fatal with an explicit message (`:562-570`).

Unit interpretation is by suffix, in `ReactionMnrlProcessConstraint` (`src/pflotran/reaction_mineral.F90:995-1011`):

| Units suffix | Meaning | Constant |
|---|---|---|
| ends with `m^3_mnrl` | m² mineral / m³ **mineral** | `MINERAL_SURF_AREA_PER_MNRL_VOL` |
| ends with `g` (e.g. `m^2/g`, `m^2/kg`) | m² mineral / kg mineral | `MINERAL_SURF_AREA_PER_MNRL_MASS` |
| ends with `m^3` | m² mineral / m³ **bulk** | `MINERAL_SURF_AREA_PER_BULK_VOL` |

Anything else is a fatal error (`:1007-1010`). A mass-based constraint area is converted to bulk-volume basis by $\times W_m/V_m$ (`:1052-1054`) and $\times \varphi_m$ (`:1058-1062`); it additionally requires nonzero, non-500 molar weight and volume (`:1038-1051` — 500 is the database's sentinel for "undefined"). If both `SPECIFIC_SURFACE_AREA` (under `MINERAL_KINETICS`) and a mass-based constraint area are given and they differ, PFLOTRAN aborts (`:1027-1033`).

Values land in `mnrl_area0` / `mnrl_volfrac0` at `src/pflotran/reaction.F90:1494-1510`, or from an external `DATASET` at `src/pflotran/condition_control.F90:1529` and `:1603`.

### 3.4 Armoring

If `UPDATE_ARMOR_MINERAL_SURFACE` is set under `CHEMISTRY` (`src/pflotran/reaction.F90:820-823`) and `ARMOR_CRIT_VOL_FRAC` > 0, the area of the armored mineral is scaled by $\bigl((\varphi_c - \varphi_{\mathrm{armor}})/\varphi_c\bigr)^{q}$ while the armoring mineral's volume fraction stays below $\varphi_c$, and is set to **zero** once it exceeds it (`src/pflotran/reaction_mineral.F90:2073-2105`). The armoring mineral is named by `ARMOR_MINERAL`. Note the exponent used is `kinmnrl_surf_area_vol_frac_pwr` (`:2095`), **not** `ARMOR_PWR` — `ARMOR_PWR` is parsed (`:211`) and stored (`src/pflotran/reaction_database.F90:2430`) but I found no read of `kinmnrl_armor_pwr` anywhere in the kinetics path. `ARMOR_PWR` appears to be dead at this commit.

---

## 4. Porosity and permeability feedback

Both are opt-in `CHEMISTRY`-level cards, parsed in `ReactionReadPass1`:

| Keyword | Line | Effect |
|---|---|---|
| `UPDATE_POROSITY` | `src/pflotran/reaction.F90:799-801` | `reaction%update_porosity = .true.`, `option%flow%transient_porosity = .true.` |
| `UPDATE_TORTUOSITY` | `:802-803` | `reaction%update_tortuosity = .true.` |
| `UPDATE_PERMEABILITY` | `:804-805` | `reaction%update_permeability = .true.` |
| `MINIMUM_POROSITY` | `:876-878` | floor on the computed porosity; default `0.d0` (`reaction_aux.F90:521`) |
| `CALCULATE_INITIAL_POROSITY` | `:797-798` | sets `reaction%calculate_initial_porosity` |
| `UPDATE_MINERAL_SURFACE_AREA` | `:806-812` | **removed** — now a fatal error directing the user to `SURFACE_AREA_FUNCTION` |
| `UPDATE_MNRL_SURF_AREA_WITH_POR` | `:813-819` | **removed** — same fatal error |

`UPDATE_POROSITY` is *required* whenever `UPDATE_TORTUOSITY`, `UPDATE_PERMEABILITY`, or any porosity-based `SURFACE_AREA_FUNCTION` is used; otherwise PFLOTRAN aborts (`src/pflotran/reaction.F90:955-966`, using `ReactionMnrlAnyUpdatePorosity`, `src/pflotran/reaction_mineral_aux.F90:748-779`).

### 4.1 Porosity from mineral volume fractions

`RealizationCalcMineralPorosity`, `src/pflotran/realization_subsurface.F90:2172-2247`:

```fortran
sum_volfrac = 0.d0
do imnrl = 1, reaction%mineral%nkinmnrl
  sum_volfrac = sum_volfrac + rt_auxvars(ghosted_id)%mnrl_volfrac(imnrl)
enddo
material_auxvars(ghosted_id)%porosity_base = &
  max(1.d0-sum_volfrac,reaction%minimum_porosity)
```
(`src/pflotran/realization_subsurface.F90:2219-2227`)

$$\phi = \max\Bigl(1 - \textstyle\sum_m \varphi_m,\;\phi_{\min}\Bigr)$$

**This is the single biggest trap in the whole subsystem.** The sum runs over **kinetic minerals only**, and porosity is computed as $1-\sum\varphi_m$ **absolutely**, not as an increment from the initial porosity. If the `CONSTRAINT / MINERALS` volume fractions do not already sum to $1-\phi_0$ (i.e. if any solid is not represented as a kinetic mineral), turning on `UPDATE_POROSITY` will discontinuously reset the porosity on the first update. The source itself flags this: the commented-out block immediately below (`:2228-2232`) is the "proposed form" $\phi = \phi_0 - \sum\varphi_m$, annotated `but it breaks geochemistry`. For a basalt column, either give every solid phase a kinetic-mineral entry summing to $1-\phi_0$, or leave `UPDATE_POROSITY` off.

Only `porosity_base` is written; the ghosted values are synchronized via PETSc's `VecScatter`-backed `DiscretizationLocalToLocal` (`:2236-2243`).

### 4.2 Permeability from porosity

`src/pflotran/realization_subsurface.F90:2055-2069`:

$$\frac{k}{k_0} \;=\; \max\!\left[\left(\frac{\phi-\phi_c}{\phi_0-\phi_c}\right)^{n},\;f_{\min}\right]$$

applied isotropically (or to all six tensor entries) at `:2070-2083`. If either $\phi$ or $\phi_0$ is at or below $\phi_c$ the scale is 0 before the `max` (`:2061-2063`). Governing `MATERIAL_PROPERTY` cards (`src/pflotran/material.F90`):

| Keyword | Line | Variable | Default |
|---|---|---|---|
| `PERMEABILITY_POWER` | `:781-784` | `permeability_pwr` ($n$) | `1.d0` (`:193`) |
| `PERMEABILITY_CRITICAL_POROSITY` | `:785-788` | `permeability_crit_por` ($\phi_c$) | `0.d0` (`:194`) |
| `PERMEABILITY_MIN_SCALE_FACTOR` | `:789-792` | `permeability_min_scale_fac` ($f_{\min}$) | `1.d0` (`:195`) |
| `TORTUOSITY_POWER` | `:793-796` | `tortuosity_pwr` | `0.d0` (`:211`) |

**Second major trap.** `permeability_min_scale_fac` defaults to **1.0** (`src/pflotran/material.F90:195`), and it is applied as a *lower* bound: `scale = max(permeability_min_scale_fac, scale)` (`src/pflotran/realization_subsurface.F90:2068-2069`). With the default, $k/k_0 \ge 1$ always — **permeability can only increase, never decrease.** A clogging (net-precipitation) scenario therefore shows no permeability reduction unless `PERMEABILITY_MIN_SCALE_FACTOR` is explicitly set to a small value. `TORTUOSITY_POWER` defaults to 0, which makes the tortuosity scale identically 1.

This is a Verma–Pruess-style power law, **not** Kozeny–Carman; with $n=3$ and $\phi_c=0$ it reduces to a cubic law. Tortuosity uses $(\phi/\phi_0)^{\texttt{tortuosity\_pwr}}$ (`src/pflotran/realization_subsurface.F90:2027-2031`) — note that one *is* a plain porosity ratio, unlike the surface-area function.

`MINERAL_SURFACE_AREA_POWER` under `MATERIAL_PROPERTY` is a removed keyword that now errors out (`src/pflotran/material.F90:797-802`).

---

## 5. Where mineral kinetics enters the solve

`ReactionMnrlKinetics` (`src/pflotran/reaction_mineral.F90:1129-1197`) zeroes `mnrl_rate`, forms `ln_conc`/`ln_act`/`ln_sec`/`ln_sec_act`, loops over kinetic minerals, and finally calls `ReactionMnrlNucleationKinetics` if any `NUCLEATION` block exists (`:1190-1195`).

The rate is converted from volumetric to absolute by multiplying by the cell volume (`:1533`, `:1537`) and accumulated into the residual with the **residual-basis** stoichiometry (`:1539-1542`):

```fortran
do i = 1, mineral%kinmnrlspecid_in_residual(0,imnrl)
  icomp = mineral%kinmnrlspecid_in_residual(i,imnrl)
  Res(icomp) = Res(icomp) + mineral%kinmnrlstoich_in_residual(i,imnrl)*Im
enddo
```

`kinmnrlspecid` (used for $Q/K$) and `kinmnrlspecid_in_residual` (used for the mass balance) are **different arrays** — the first is in the full basis including species that were decoupled, the second is the set actually carried as transported components.

The analytical Jacobian is `:1544-1715`, including a hand-coded correction for the sign discontinuity introduced by the `sign_`/`dabs` split when `AFFINITY_POWER` is used (`:1553-1557`).

State update (volume fraction advance) happens once per timestep in `ReactionMnrlUpdateKineticState` (`:2124-2206`), called from `RUpdateKineticState` (`src/pflotran/reaction.F90:5741`). It calls the rate routine again with `store_rate = .true.` and `compute_analytical_derivative = .false.` (`:2151-2152`), so the volume-fraction advance is **explicit** in the mineral volume fraction over the transport step.

---

## 6. Calibration knobs summary

| Deck keyword | Parse line | Units | Default | Physically controls |
|---|---|---|---|---|
| `RATE_CONSTANT` | `reaction_mineral.F90:159` | mol m⁻² s⁻¹ (or $\log_{10}$ if negative) | none (required) | overall rate magnitude, both directions |
| `PRECIPITATION_RATE_CONSTANT` | `:159` | mol m⁻² s⁻¹ | — | precipitation branch only |
| `DISSOLUTION_RATE_CONSTANT` | `:159` | mol m⁻² s⁻¹ | — | dissolution branch only |
| `ACTIVATION_ENERGY` | `:174` | J mol⁻¹ | 0 (no T dependence) | Arrhenius temperature sensitivity about 25 °C |
| `AFFINITY_THRESHOLD` | `:181` | $Q/K$, dimensionless | 0 (off) | supersaturation needed before precipitation starts |
| `AFFINITY_POWER` | `:185` | dimensionless | 1 | nonlinearity of rate in $|1-Q/K|$; >1 slows near-equilibrium rates |
| `TEMKIN_CONSTANT` | `:193` | dimensionless | 1 | stoichiometric number $\sigma$ in $(Q/K)^{1/\sigma}$ |
| `MINERAL_SCALE_FACTOR` | `:189` | dimensionless | 1 | rescales reaction stoichiometry: divides area *and* stretches affinity |
| `RATE_LIMITER` | `:203` | dimensionless | 0 (off) | caps the precipitation affinity factor (max rate $\approx A_m k r/s$) |
| `SURFACE_AREA_FUNCTION` | `:331` | enum | `CONSTANT` | whether/how $A_m$ evolves |
| `SURFACE_AREA_POROSITY_POWER` | `:197` | dimensionless | required by fn. | exponent on solid-fraction ratio $(1-\phi)/(1-\phi_0)$ |
| `SURFACE_AREA_VOL_FRAC_POWER` | `:200` | dimensionless | required by fn. | exponent on $\varphi_m/\varphi_m^0$; 2/3 = geometric shrinking-sphere |
| `SPECIFIC_SURFACE_AREA` | `:353` | m² kg⁻¹ | uninit. | BET area for `SURFACE_AREA_FUNCTION MINERAL_MASS` |
| `SPECIFIC_SURFACE_AREA_EPSILON` | `:218` | m² m⁻³ bulk | 0 | floor on base area (lets a depleted mineral re-grow) |
| `VOLUME_FRACTION_EPSILON` | `:221` | m³ m⁻³ | 0 | floor on $\varphi_m$ inside the ratio (same purpose) |
| `PREFACTOR` / `ALPHA` | `:224`/`:279` | dimensionless | 0 | pH (or other species) exponent of a parallel pathway |
| `PREFACTOR` / `BETA` | `:283` | dimensionless | 0 | exponent in the attenuation denominator |
| `PREFACTOR` / `ATTENUATION_COEF` | `:287` | dimensionless | 0 | saturation coefficient $c_j$ of the pathway |
| `ARMOR_CRIT_VOL_FRAC` | `:215` | m³ m⁻³ | 0 (off) | volume fraction of the armoring phase that shuts the surface off |
| constraint vol. frac. (col. 2) | `transport_constraint_rt.F90:528` | m³ m⁻³ | none (required) | initial mineral abundance; sets $\varphi_m^0$ |
| constraint area (col. 3) | `transport_constraint_rt.F90:546` | per units word, default m² m⁻³ bulk | none (required) | initial reactive area $A_m^0$ — usually the dominant uncertainty |
| `MINIMUM_POROSITY` | `reaction.F90:876` | m³ m⁻³ | 0 | floor when `UPDATE_POROSITY` is on |
| `PERMEABILITY_POWER` | `material.F90:781` | dimensionless | 1 | exponent $n$ in $k/k_0$ |
| `PERMEABILITY_CRITICAL_POROSITY` | `material.F90:785` | m³ m⁻³ | 0 | percolation threshold $\phi_c$ |

Rough sensitivity ordering for a weathering column: constraint surface area $\approx$ `RATE_CONSTANT` (they multiply, so they are perfectly correlated far from equilibrium and cannot be identified separately from bulk effluent chemistry alone) $>$ `PREFACTOR`/`ALPHA` pH dependence $>$ `ACTIVATION_ENERGY` (only if the column is non-isothermal) $>$ `SURFACE_AREA_VOL_FRAC_POWER` $>$ `AFFINITY_POWER` (matters only once a phase approaches saturation) $>$ `AFFINITY_THRESHOLD`/`RATE_LIMITER` (secondary phases only).

## 7. Things I could not verify

- `ARMOR_PWR` is parsed and stored but I found no read of `kinmnrl_armor_pwr` in the rate or surface-area path; the armoring exponent actually used is `kinmnrl_surf_area_vol_frac_pwr` (`reaction_mineral.F90:2095`). Whether this is intentional is not determinable from static reading.
- `NUCLEATION_KINETICS` / the `NUCLEATION` block (`reaction_mineral.F90:686`, kinetics at `:1721-1896`) is new at this commit (author date 01/20/25–01/25) and is not covered here.
- The interaction between `MINERAL_SCALE_FACTOR` and `AFFINITY_POWER` (both rescale the affinity term) is not guarded by any consistency check; their combined behavior is not obvious from static reading.
