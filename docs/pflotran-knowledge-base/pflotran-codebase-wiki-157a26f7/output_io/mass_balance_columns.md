**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** OUTPUT / MASS_BALANCE_FILE — the per-column catalog of `*-mas.dat`
**Last verified:** 2026-07-31

# `-mas.dat` Column Catalog

Companion to `mass_balance_file.md`, which covers file mechanics, parsing, and
the sign / cumulative-versus-rate semantics. This page enumerates **which
columns exist, in what order, with what names and units**, per flow and
transport mode.

All line references are into `OutputMassBalance`
(`src/pflotran/output_observation.F90:2326`). The header block and the data block
walk the same conditional chain in the same order; both line ranges are given so
a reader can confirm alignment.

---

## 0. Family emission order

| # | Family | Header | Data |
|---|---|---|---|
| 1 | `Time [<tunit>]` | `:2447-2448` | `:2979` |
| 2 | `dt_flow [<tunit>]`, only if `iflowmode > 0` | `:2450-2452` | `:2982-2985` |
| 3 | `dt_tran [<tunit>]`, only if `ntrandof > 0` | `:2454-2456` | `:2986-2989` |
| 4 | `Global ...` flow inventories | `:2458-2526` | `:3038-3080` |
| 5 | `Global <species>` transport inventories | `:2528-2596` | `:3083-3186` |
| 6 | per-coupler (BCs, then source/sinks) | `:2598-2762` | `:3189-3624` |
| 7 | `Well <name> ...` | `:2765-2818` | `:3626-3747` |
| 8 | `Region <name> ...` | `:2822-2966` | `:3750-3934` |

The presence of `dt_tran` is a cheap runtime test for whether transport is
active, which in turn tells you whether families 5 and the transport half of 6
exist at all.

---

## 1. `Global ...` — domain-wide inventories

### 1.1 Flow (`src/pflotran/output_observation.F90:2458-2526`)

| `iflowmode` | Columns emitted | Lines |
|---|---|---|
| `RICHARDS_MODE`, `RICHARDS_TS_MODE`, `PNF_MODE` | `Global Water Mass [kg]` | `:2459-2460` |
| `ZFLOW_MODE` | `Global Water Volume [m^3]` | `:2461-2462` |
| `TH_MODE`, `TH_TS_MODE` | `Global Water Mass in Liquid Phase [kg]` | `:2463-2465` |
| `H_MODE` | water/air in liquid, water/air in gas, all `[kg]` | `:2466-2474` |
| `G_MODE` | water/air in liquid `[kg]`; if `nphase > 2` also salt in liquid, water/air in gas, `Global Salt Mass in Precipitate`; else water/air in gas | `:2475-2494` |
| `WF_MODE` | `Global Water Mass in Liquid Phase [kg]`, `Global Gas Component Mass in Gas Phase [kg]` | `:2495-2499` |
| `MPH_MODE` | six `[kmol]` columns: water/CO2 in water phase, `Trapped CO2 Mass in Water Phase`, water/CO2 in gas phase, `Trapped CO2 Mass in Gas Phase` | `:2500-2512` |
| `SCO2_MODE` | six `[kg]` columns incl. `Global Trapped CO2 Mass` | `:2513-2525` |

Values come from the per-mode `*ComputeMassBalance` routines
(`src/pflotran/output_observation.F90:2996-3024`), MPI-reduced onto the I/O rank
(`:3027-3028`), and written with **no sign flip** (`:3038-3080`). Note the
per-mode write loops apply their own index filters — `G_MODE` skips
`(iphase,ispec)` combinations at `:3050-3052`, `SCO2_MODE` at `:3071-3075` — so
the data loop, not `nflowspec × nphase`, determines the count.

### 1.2 Transport, `RT_MODE` (`src/pflotran/output_observation.F90:2528-2575`)

In order:

1. one `Global <species>` per printed aqueous primary species, gated on
   `reaction%primary_species_print(i)` (`:2531-2540`), data from
   `sum_mol_global(icomp,1)` (`:3117-3121`)
2. one per printed immobile species, gated on `reaction%immobile%print_me(i)`
   (`:2542-2551`), data from `sum_mol_global(i,7)` (`:3123-3128`)
3. one per printed active gas, gated on `reaction%gas%active_print_me(i)`
   (`:2553-2562`), data from `sum_mol_global(i,8)` (`:3130-3135`)
4. **only if `option%mass_bal_detailed`** — one per printed kinetic mineral,
   gated on `reaction%mineral%kinmnrl_print(i)` (`:2564-2575`), data from
   `sum_mol_global(i,6)` (`:3138-3146`)

Units are `kg` if `reaction%print_total_mass_kg` else `mol`
(`src/pflotran/output_observation.F90:2534-2538`).

### 1.3 Transport, `NWT_MODE` (`src/pflotran/output_observation.F90:2576-2594`)

Per species, up to four `[mol]` columns, each gated on its own print flag:

| Column suffix | Flag | Header line | Data |
|---|---|---|---|
| `<species> Total Bulk ` | `print_what%total_bulk_conc` | `:2578-2581` | `:3170-3172` |
| `<species> Aqueous ` | `print_what%aqueous_eq_conc` | `:2582-2585` | `:3173-3175` |
| `<species> Sorbed ` | `print_what%sorb_eq_conc` | `:2586-2589` | `:3176-3178` |
| `<species> Mineral ` | `print_what%mnrl_eq_conc` | `:2590-2593` | `:3179-3181` |

Note the **trailing space** in the constructed name, e.g.
`'Global ' // species // ' Total Bulk '` (`:2579`), which
`OutputWriteToHeader`'s `adjustl`/`trim` handling removes before quoting
(`src/pflotran/output_aux.F90:1378-1385`).

---

## 2. Per-coupler flux columns

### 2.1 Which couplers, in what order

One block per coupler, iterating **boundary conditions first, then
source/sinks**. Header loop at `src/pflotran/output_observation.F90:2598-2614`,
data loop at `:3189-3224` — the two are structurally identical, which is what
guarantees alignment:

```fortran
      coupler => patch%boundary_condition_list%first
      bcs_done = PETSC_FALSE
      do
        if (.not.associated(coupler)) then
          if (bcs_done) then
            exit
          else
            bcs_done = PETSC_TRUE
            if (associated(patch%source_sink_list)) then
              coupler => patch%source_sink_list%first
              if (.not.associated(coupler)) exit
              if (.not.output_option%print_ss_massbal) exit
```
(`src/pflotran/output_observation.F90:2598-2609`)

Source/sinks are skipped entirely when `NO_PRINT_SOURCE_SINK` cleared
`print_ss_massbal` (`src/pflotran/output.F90:196-197`; skip at `:2609` header,
`:3210` data).

Column names are `<coupler%name> <quantity>` — the coupler name is the
BOUNDARY_CONDITION / SOURCE_SINK name from the deck, which is why the motivating
run shows families named `east`, `top_vent`, `top_recharge`.

### 2.2 Flow columns — cumulative first, then rate

For each coupler and each flow species, **two columns**: cumulative, then rate.
For `RICHARDS_MODE, RICHARDS_TS_MODE, PNF_MODE`:

```fortran
          case(RICHARDS_MODE,RICHARDS_TS_MODE,PNF_MODE)
            string = trim(coupler%name) // ' Water Mass'
            call OutputWriteToHeader(fid,string,'kg','',icol)
            units = 'kg/' // trim(output_option%tunit) // ''
            string = trim(coupler%name) // ' Water Mass'
            call OutputWriteToHeader(fid,string,units,'',icol)
```
(`src/pflotran/output_observation.F90:2617-2622`)

**The two columns have the identical name and differ only in the units
bracket** — `"east Water Mass [kg]"` versus `"east Water Mass [kg/h]"`. An
extractor must key on the units string, not the name.

| `iflowmode` | Per-coupler flow columns | Header | Data |
|---|---|---|---|
| `RICHARDS_*`, `PNF_MODE` | Water Mass `[kg]`, Water Mass `[kg/t]` | `:2617-2622` | `:3276-3315` |
| `ZFLOW_MODE` | Water Volume `[m^3]`, `[m^3/t]` | `:2623-2628` | `:3276-3315` |
| `TH_MODE`, `TH_TS_MODE` | Water Mass `[kg]`, `[kg/t]` | `:2629-2634` | `:3317-3350` |
| `H_MODE` | Water, Air `[kg]`; Water, Air `[kg/t]` | `:2635-2644` | `:3434-3468` |
| `G_MODE` | Water, Air `[kg]`, `[+ Salt if nphase>2]`; then the same in `[kg/t]` | `:2645-2665` | `:3434-3468` |
| `WF_MODE` | Water Mass, Gas Component Mass `[kg]`; then `[kg/t]` | `:2666-2676` | `:3469-3503` |
| `MPH_MODE` | Water Mass, CO2 Mass `[kmol]`; then `[kmol/t]` | `:2677-2687` | `:3352-3395` |
| `SCO2_MODE` | Water Mass, CO2 Mass `[kg]`; then `[kg/t]` | `:2688-2698` | `:3396-3433` |

Cumulative columns for all species come first, then rate columns for all species
— not interleaved per species. Verify against the `G_MODE` header at
`:2645-2665`, which emits water/air/[salt] in `kg` before water/air/[salt] in
`kg/<tunit>`.

For `MPH_MODE` note the source comment at
`src/pflotran/output_observation.F90:3381-3382`: the `kmol`→`kg` conversion for
the rate is commented out with `! <<---fix for multiphase!`, so `MPH_MODE`
per-coupler rate columns are in `kmol/<tunit>` as the header says, unconverted.

### 2.3 Transport columns, `RT_MODE` (`src/pflotran/output_observation.F90:2701-2743`)

Per coupler, in order:

1. cumulative `[mol]`, one per printed aqueous species (`:2704-2710`), data at
   `:3527-3531`
2. **only if `reaction%gas%nactive_gas > 0`** — a parallel set named
   `<coupler> <species> (gas phase)` in `[mol]` (`:2713-2722`), data at
   `:3535-3541`. The source comment explains the alignment:
   `! this block prints out the contribution to the total component flux in the
   gas phase. it must be aligned with the aqueous components, not gases`
   (`src/pflotran/output_observation.F90:3532-3534`) — so the count is
   `naqcomp`, not `nactive_gas`.
3. the same two groups again in `[mol/<tunit>]` (`:2724-2743`), data at
   `:3556-3574`

So a coupler's transport width is `2·N` when `nactive_gas == 0` and `4·N` when
`nactive_gas > 0`, where `N` is the number of printed aqueous primary species.

### 2.4 Transport columns, `NWT_MODE` (`src/pflotran/output_observation.F90:2745-2757`)

One `[mol]` column per species, then one `[mol/<tunit>]` column per species. No
gas-phase duplication and no per-species print gate on the header side
(`:2746-2750`, `:2753-2756`); data at `:3595-3597` and `:3614-3617`.

---

## 3. `Well <name> ...`

Emitted only when `patch%well_coupler_list` is associated
(`src/pflotran/output_observation.F90:2765` header, `:3627` data).

| Column | Units | Header | Data |
|---|---|---|---|
| `Well <well_name> Total Water Mass` | `kg` | `:2769-2770` | `:3687-3690` |
| `Well <well_name> Total Gas Mass` | `kg` | `:2771-2772` | `:3687-3690` |
| `Well <well_name> Total <species>` | `mol` | `:2775-2781` | `:3701-3705` |
| `Well <well_name> Total <species> (gas phase)` (if `nactive_gas > 0`) | `mol` | `:2784-2793` | `:3709-3715` |
| `Well <well_name> Total <species>` | `mol/<tunit>` | `:2796-2802` | `:3726-3731` |
| `Well <well_name> Total <species> (gas phase)` | `mol/<tunit>` | `:2805-2814` | `:3736-3741` |

**Sign caveat:** the two flow columns are written **unnegated**
(`src/pflotran/output_observation.F90:3689`) despite the
`! change sign for positive in / negative out` comment at `:3688`, while the
transport columns are negated normally. See `mass_balance_file.md` §3.1.

---

## 4. `TOTAL_MASS_REGIONS` — the `Region ...` family

### 4.1 Declaration and binding

Deck syntax is a nested list of region names:

```fortran
      case('TOTAL_MASS_REGIONS')
        ...
          case('MASS_BALANCE_FILE')
            string = 'OUTPUT,' // trim(block_name) // ',TOTAL_MASS_REGIONS'
            output_option%mass_balance_region_flag = PETSC_TRUE
```
(`src/pflotran/output.F90:200-212`), each name creating a
`mass_balance_region_type` appended to `output_option%mass_balance_region_list`
(`src/pflotran/output.F90:222-240`). Rejected inside `OBSERVATION_FILE` and
`SNAPSHOT_FILE` (`src/pflotran/output.F90:202-209`).

Each named region must already exist as a `REGION`. Binding happens in
`PatchGetCompMassInRegionAssign` (`src/pflotran/patch.F90:11605`), called when
the flag is set (`src/pflotran/factory_subsurface.F90:553-556`):

```fortran
    if (.not.success) then
      option%io_buffer = 'Region ' // trim(cur_mbr%region_name) // ' not &
                          &found among listed regions.'
      call PrintErrMsg(option)
    endif
    ! Assign the mass balance region the wanted region's info:
    cur_mbr%num_cells = cur_region%num_cells
    cur_mbr%region_cell_ids => cur_region%cell_ids
```
(`src/pflotran/patch.F90:11640-11647`)

Region matching is case-insensitive (`StringCompareIgnoreCase`,
`src/pflotran/patch.F90:11635`), but the header string uses the name **as typed
in `TOTAL_MASS_REGIONS`** (`cur_mbr%region_name`, set at
`src/pflotran/output.F90:223`), not the canonical `REGION` name.

### 4.2 Flow columns per region

| `iflowmode` | Columns | Header | Data |
|---|---|---|---|
| `RICHARDS_*`, `TH_*`, `PNF_MODE` | `Region <name> Water Mass [kg]` | `:2826`, `:2874-2875` | `:3779-3782`, `:3796-3809` |
| `G_MODE` | `Region <name> Water Mass [kg]`, then a doubled-literal air column, then salt if `nphase > 2` | `:2866-2873` | `:3762-3764`, `:3796-3809` |
| `SCO2_MODE` | twelve `[kg]` columns with a **bare region name** (no `Region ` prefix): `<name> Aqueous Phase Water Mass`, `... Gas Phase Water Mass`, `... Salt Precip. Water Mass`, `... Trapped Gas Water Mass`, and the same four for CO2 and for Salt | `:2829-2865` | `:3766-3777`, `:3810-3822` |
| anything else | fatal | — | `:3783-3787` |

The fatal message is
`'Calculation of water mass in TOTAL_MASS_REGIONS not supported for the
specified flow mode.'` (`src/pflotran/output_observation.F90:3784-3786`).

**Known source bug, `G_MODE` air column.** The name is concatenated twice:

```fortran
              case(G_MODE)
                call OutputWriteToHeader(fid,string,'kg','',icol)
                string = 'Region ' // trim(cur_mbr%region_name) // ' Air Mass'
                call OutputWriteToHeader(fid,string // ' Air Mass','kg','',icol)
```
(`src/pflotran/output_observation.F90:2866-2869`)

producing the literal `Region <name> Air Mass Air Mass`. Parse it literally.

### 4.3 Transport columns per region, `RT_MODE` (`:2880-2932`)

1. `Region <name> Total Mass` (`:2881-2886`) — data is the **sum** over all rows
   of `global_total_mass(:,1)` (`:3850-3856`), i.e. the sum of the per-species
   columns that follow
2. `Region <name> <species> Mass` per printed aqueous species (`:2887-2897`),
   data `:3857-3861`
3. `Region <name> <immobile> Mass` (`:2898-2908`), data `:3863-3868`
4. `Region <name> <gas> Mass` (`:2910-2920`), data `:3870-3875`
5. `Region <name> <mineral> Total Mass` (`:2922-2932`), data `:3876-3880` —
   **emitted unconditionally**, unlike the `Global` mineral columns which require
   `DETAILED`

Units `kg` or `mol` per `reaction%print_total_mass_kg` throughout.

### 4.4 Transport columns per region, `NWT_MODE` (`:2934-2960`)

`Region <name> Total Mass [mol]` (`:2935-2936`, data `:3906-3912`), then per
species — gated on `reaction_nw%species_print(i)` (`:2938`) — up to four columns:
`Total Bulk Mass`, `Aqueous Mass`, `Sorbed Mass`, `Mineral Mass`, each on its own
`print_what` flag (`:2939-2958`), data `:3913-3927`.

Note the header gates on `species_print(i)` while the **data loop does not**
(`src/pflotran/output_observation.F90:3913-3927` has no `species_print` test).
If any species has `species_print = .false.`, the NWT region header and data
would misalign. Flagged as a source inconsistency; I did not run the code to
confirm the consequence.

---

## 5. Deriving the column count

The width is a function of runtime state, not deck text alone:

```
width = 1                                   (Time)
      + [1 if nflowdof > 0]                 (dt_flow)
      + [1 if ntrandof  > 0]                (dt_tran)
      + G_flow(iflowmode, nphase)           (§1.1)
      + G_tran(naqcomp, nimmobile, ngas, [nmineral if DETAILED])   (§1.2/1.3)
      + Σ_couplers [ C_flow(iflowmode, nphase) + C_tran(naqcomp, ngas) ]  (§2)
      + Σ_wells    [ W(naqcomp, ngas) ]     (§3)
      + Σ_regions  [ R_flow(iflowmode) + R_tran(...) ]              (§4)
```

`naqcomp` counts only species with `primary_species_print(i) == .true.`, which is
set by the CHEMISTRY block, not by `OUTPUT`. `nphase` and `nflowspec` come from
the flow mode. The coupler list includes every `BOUNDARY_CONDITION` **and**
every `SOURCE_SINK` unless `NO_PRINT_SOURCE_SINK` is set.

**Do not compute this — read the header.** It is emitted by the same conditional
chain as the data and is therefore always correct for the run that produced it.
