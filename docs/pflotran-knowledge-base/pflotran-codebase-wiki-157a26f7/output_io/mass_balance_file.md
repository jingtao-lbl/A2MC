**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** OUTPUT / MASS_BALANCE_FILE (`*-mas.dat`) — file mechanics, parsing, sign and rate semantics
**Last verified:** 2026-07-31

# The Mass Balance File (`pflotran-mas.dat`)

This is the file an extraction layer should target first: it is the only PFLOTRAN
output that reports **global inventories, per-coupler cumulative fluxes,
per-coupler flux rates, and per-region total masses** in one time-ordered table.

The per-column catalog (which families exist, in what order, with what names and
units, per flow/transport mode) is in the companion page
**`mass_balance_columns.md`**. This page covers how the file is produced, how to
parse it, and what the numbers mean.

Everything is emitted by a single routine, `OutputMassBalance`
(`src/pflotran/output_observation.F90:2326`), which despite its name and its
comment `! Print to Tecplot POINT format`
(`src/pflotran/output_observation.F90:2328`) writes a plain text table, not a
Tecplot zone.

---

## 1. Enabling it, and the file name

`MASS_BALANCE_FILE` is a sub-block of `OUTPUT`. It is dispatched at
`src/pflotran/factory_subsurface_read.F90:1808` into the shared reader
`OutputFileRead` (`src/pflotran/output.F90:68`), whose first act for this block is

```fortran
    case('MASS_BALANCE_FILE')
      option%compute_mass_balance_new = PETSC_TRUE
```
(`src/pflotran/output.F90:136-137`)

A legacy one-line form also exists, `OUTPUT / MASS_BALANCE [DETAILED]`
(`src/pflotran/factory_subsurface_read.F90:1846-1861`), which additionally forces
`periodic_msbl_output_ts_imod = 1`
(`src/pflotran/factory_subsurface_read.F90:1848`) — i.e. legacy `MASS_BALANCE`
writes **every timestep**, while the new `MASS_BALANCE_FILE` block writes only
when its own timing keywords say so (§4).

File name (`src/pflotran/output_observation.F90:2427-2432`):

```fortran
  if (len_trim(output_option%plot_name) > 2) then
    filename = trim(output_option%plot_name) // '-mas.dat'
  else
    filename = trim(option%global_prefix) // trim(option%group_prefix) // &
               '-mas.dat'
  endif
```

Default is `<global_prefix><group_prefix>-mas.dat`, i.e. `pflotran-mas.dat` for a
deck named `pflotran.in`. There is **no** plot-number suffix — one file for the
whole run, appended to.

Open mode (`src/pflotran/output_observation.F90:2443-2444`, `:2969`):

```fortran
    if (mass_balance_first .or. .not.FileExists(filename)) then
      open(unit=fid,file=filename,action="write",status="replace")
      ...
    else
      open(unit=fid,file=filename,action="write",status="old",position="append")
```

`mass_balance_first` is true only when `num_steps == 0`
(`src/pflotran/output_observation.F90:53-57`) and is cleared after the first
write (`src/pflotran/output_observation.F90:3941`).

**Consequence for an extractor:** on a **restart** (`num_steps /= 0`) the run
appends to an existing `-mas.dat` and emits **no second header**. Combined with
`RESET_TO_TIME_ZERO` (see `checkpoint_restart.md` §4.2) this yields a
non-monotonic `Time` column. Always check monotonicity before treating the file
as a single time series.

Only the I/O rank writes: every `write(fid,...)` is guarded by
`OptionIsIORank(option)` (e.g. `src/pflotran/output_observation.F90:2435`,
`:2978`, `:3038`, `:3936`). Unlike the observation `.pft` files, there is one
`-mas.dat` per run, not one per rank.

---

## 2. File layout: header is CSV-ish, data rows are NOT

This is the single most important parsing fact.

### 2.1 Header line

One line, comma-separated, every field double-quoted. The first field is preceded
by a single space and **no** comma:

```fortran
      write(fid,'(a)',advance="no") ' "Time [' // trim(output_option%tunit) // &
        ']"'
```
(`src/pflotran/output_observation.F90:2447-2448`)

Every subsequent column is appended by `OutputWriteToHeader`
(`src/pflotran/output_aux.F90:1358`), which prefixes a comma *inside* the quoted
token's format string:

```fortran
    write(string,'('',"'',a,a,'' ['',a,''] '',a,''"'')') trim(column_string), &
          trim(variable_string_adj), trim(units_string_adj), &
          trim(cell_string_adj)
  else if (len_units > 0 .or. len_cell_string > 0) then
    if (len_units > 0) then
      write(string,'('',"'',a,a,'' ['',a,'']"'')') trim(column_string), &
            trim(variable_string_adj), trim(units_string_adj)
```
(`src/pflotran/output_aux.F90:1399-1405`; the no-units form at `:1411-1412`)

So each header token is literally `,"<colid><name> [<units>]"`. The mass-balance
call sites always pass an empty `cell_string`
(e.g. `src/pflotran/output_observation.F90:2460`), so the three-argument form at
`:1399` never fires here and every column reads `"<name> [<units>]"`.

`<colid>` appears only when `PRINT_COLUMN_IDS` was given
(`src/pflotran/output.F90:542-543`), in which case `icol` starts at 1
(`src/pflotran/output_observation.F90:2437-2438`) and each column is prefixed
`"<n>-"` via `write(column_string,'(i4,''-'')') icolumn`
(`src/pflotran/output_aux.F90:1387-1390`). Without it, `icol = -1`
(`src/pflotran/output_observation.F90:2440`) and no prefix appears.

The header line is terminated by `write(fid,'(a)') ''`
(`src/pflotran/output_observation.F90:2967`).

### 2.2 Data rows

Fixed-width Fortran, **no commas**:

```fortran
100 format(100es16.8)
110 format(100es16.8)
```
(`src/pflotran/output_observation.F90:2974-2975`)

Every value is written with `advance="no"` using one of these
(e.g. `src/pflotran/output_observation.F90:2979`, `:3044`, `:3290`), and the row
is terminated by `write(fid,'(a)') ''`
(`src/pflotran/output_observation.F90:3937`).

### 2.3 Extraction rule

Split the **header** on commas and strip quotes; split each **data row** on
whitespace, or slice at 16-character boundaries. Do **not** feed the data rows to
a CSV reader.

`es16.8` is 16 characters wide. A value needing more width (e.g. a three-digit
exponent) will be rendered as `****************` by the Fortran runtime, so a
robust parser should treat an all-`*` field as missing rather than failing.

The header and the data section walk the *same* conditional chain in the *same*
order, which is what guarantees alignment. That also means the header is
authoritative — see §5.

---

## 3. Semantics: sign convention and cumulative-versus-rate

### 3.1 Boundary and source/sink fluxes are positive INTO the domain

Stated in the source at every write site, uniformly across flow modes and
transport. Representative (`src/pflotran/output_observation.F90:3288-3291`):

```fortran
          if (OptionIsIORank(option)) then
            ! change sign for positive in / negative out
            write(fid,110,advance="no") -sum_kg_global
          endif
```

The same comment-plus-negation appears at `:3312-3315`, `:3329-3332`,
`:3347-3350`, `:3367-3370`, `:3391-3394`, `:3410-3413`, `:3429-3432`,
`:3446-3449`, `:3465-3468`, `:3481-3484`, `:3500-3503` (flow) and at
`:3525-3542`, `:3556-3575`, `:3593-3598`, `:3612-3618` (transport).

So **a positive value means mass entered the domain through that coupler; a
negative value means mass left.** The internally accumulated `mass_balance` /
`mass_balance_delta` auxiliary variables carry the opposite sign; the negation is
applied only at write time.

`Global ...` and `Region ...` columns are **inventories**, not fluxes, and are
written **without** any sign flip
(`src/pflotran/output_observation.F90:3038-3080`, `:3804-3822`).

**Documented exception:** the well-coupler *flow* columns are written **without**
the negation despite carrying the same comment —

```fortran
        if (OptionIsIORank(option)) then
        ! change sign for positive in / negative out
          write(fid,110,advance="no") sum_kg_global(icomp,1)
        endif
```
(`src/pflotran/output_observation.F90:3687-3690`)

The well *transport* columns are negated as usual (`:3699-3716`, `:3724-3743`).
Treat `Well <name> Total Water/Gas Mass` as opposite in sign to boundary columns
until confirmed against a run.

### 3.2 Cumulative columns

Units bracket has no slash (`[kg]`, `[kmol]`, `[mol]`, `[m^3]`). These sum
`global_auxvars%mass_balance` over the coupler's connections and negate:

```fortran
          sum_kg = 0.d0
          do iconn = 1, coupler%connection_set%num_connections
            sum_kg = sum_kg + global_auxvars_bc_or_ss(offset+iconn)%mass_balance
          enddo
          ...
            write(fid,110,advance="no") -sum_kg_global
```
(`src/pflotran/output_observation.F90:3277-3290`)

`mass_balance` is a running total accumulated once per timestep by the flow
process model. For Richards
(`RichardsUpdateMassBalancePatch`, `src/pflotran/richards.F90:571-578`):

```fortran
      global_auxvars_bc(iconn)%mass_balance = &
        global_auxvars_bc(iconn)%mass_balance + &
        global_auxvars_bc(iconn)%mass_balance_delta* &
        richards_density_kmol_to_kg*option%flow_dt
```

That is, `mass_balance += rate × dt`, in kg. It is **never reset** during a run
(only `mass_balance_delta` is, `src/pflotran/richards.F90:514-523`), so a
cumulative column is a running integral from the start of the simulation.

### 3.3 Rate columns

Units bracket has a slash (`[kg/<tunit>]`, `[mol/<tunit>]`, `[m^3/<tunit>]`).
These sum `mass_balance_delta`, convert molar→mass, negate, and scale by `tconv`:

```fortran
          ! print out H2O flux
          sum_kg = 0.d0
          do iconn = 1, coupler%connection_set%num_connections
            sum_kg = sum_kg + global_auxvars_bc_or_ss(offset+iconn)%mass_balance_delta
          enddo

          ! mass_balance_delta units = delta kmol h2o; must convert to delta kg h2o
          select case(option%iflowmode)
            case(RICHARDS_MODE,RICHARDS_TS_MODE)
              sum_kg = sum_kg*richards_density_kmol_to_kg
            case(ZFLOW_MODE,PNF_MODE)
              sum_kg = sum_kg*FMWH2O
          end select
          ...
            write(fid,110,advance="no") -sum_kg_global*output_option%tconv
```
(`src/pflotran/output_observation.F90:3293-3315`)

`mass_balance_delta` is zeroed at the start of every flow step
(`src/pflotran/richards.F90:516`, `:521`) and holds a **per-second** rate. The
`× tconv` converts per-second to per-`TIME_UNITS`. `tconv` is
`UnitsConvertToInternal(<tunit>,'sec',...)`
(`src/pflotran/factory_subsurface_read.F90:1816-1818`), i.e. *seconds per output
time unit* — 3600 for `TIME_UNITS h`. The same factor is used to **divide**
simulated time on the way out (`option%time/output_option%tconv`,
`src/pflotran/output_observation.F90:2979`), which confirms the direction.

A rate column is therefore the **instantaneous** flux at the output time, not an
interval average.

### 3.4 Classification table

| Family | Units bracket | Meaning | Sign |
|---|---|---|---|
| coupler (`east`, `top_vent`, ...) | no slash | cumulative integral since t=0 | + into domain |
| coupler | has `/` | instantaneous rate at the output time | + into domain |
| `Global ...` | no slash | instantaneous domain-wide inventory | as computed, no flip |
| `Region <name> ...` | no slash | instantaneous inventory in that region | as computed, no flip |
| `Well <name> ...` flow | no slash | cumulative | **not** flipped — see §3.1 |
| `Well <name> ...` transport | either | cumulative / rate | + into domain |

Because both a cumulative coupler column and a `Global` inventory column can
carry the units `kg`, **the family prefix must be used together with the units**
to classify a column. The family prefix is the coupler/region name, which comes
from the deck.

---

## 4. Keywords accepted inside `MASS_BALANCE_FILE`

Parsed by the shared `OutputFileRead` (`src/pflotran/output.F90:68`):

| Keyword | Line | Effect |
|---|---|---|
| `PERIODIC TIME <v> <unit>` | `:277-291` | sets `periodic_msbl_output_time_incr` (`:289-290`) |
| `PERIODIC TIME <v> <unit> between <a> and <b>` | `:294-347` | materializes waypoints in `[a,b]`, then **zeroes** the increment (`:337-346`) |
| `PERIODIC TIMESTEP <n>` | `:354-367` | sets `periodic_msbl_output_ts_imod` (`:363-365`) |
| `TIMES <unit> <list>` | `:245-267` | one waypoint per listed time (`:262-263`) |
| `NO_PRINT_SOURCE_SINK` | `:186-198` | clears `print_ss_massbal` (`:197`) |
| `DETAILED` | `:546-550` | sets `option%mass_bal_detailed` |
| `TOTAL_MASS_REGIONS` | `:200-242` | region list, see `mass_balance_columns.md` §4 |
| `PRINT_INITIAL` / `NO_INITIAL` / `NO_PRINT_INITIAL` | `:164-183` | toggles `print_initial_massbal` |
| `NO_FINAL` / `NO_PRINT_FINAL` | `:153-161` | clears `print_final_massbal` (inert, see below) |
| `PRINT_COLUMN_IDS` | `:542-543` | prefixes header tokens with `<n>-` |

Defaults (`src/pflotran/output_aux.F90:205-207`, `:241-247`):
`print_initial_massbal = PETSC_FALSE`, `print_final_massbal = PETSC_TRUE`,
`print_ss_massbal = PETSC_TRUE`, `periodic_msbl_output_ts_imod = 100000000`,
`periodic_msbl_output_time_incr = 0`.

`TIME_UNITS` is a **top-level `OUTPUT` keyword**, not a `MASS_BALANCE_FILE` one
(`src/pflotran/factory_subsurface_read.F90:1811-1818`). Changing `TIME_UNITS h`
to `TIME_UNITS d` changes both the `Time` column's scale and the numeric value of
every rate column. Full timing semantics are in `output_timing.md`.

### What `DETAILED` adds

```fortran
      case('DETAILED')
        select case(trim(block_name))
          case('MASS_BALANCE_FILE')
            option%mass_bal_detailed = PETSC_TRUE
        end select
```
(`src/pflotran/output.F90:546-550`)

Its only effect in this file is to add **global kinetic-mineral inventory
columns** for RT_MODE — header at `src/pflotran/output_observation.F90:2564-2575`,
data at `:3138-3146` from `sum_mol_global(i,6)`. Note the asymmetry: the
**per-region** mineral columns are emitted *unconditionally*, not gated on
`DETAILED` (`src/pflotran/output_observation.F90:2922-2932` header, `:3876-3880`
data). So `DETAILED` changes the `Global` family only.

### `VARIABLES` and `FORMAT` are rejected

Both are hard errors inside `MASS_BALANCE_FILE`:

```fortran
          case('MASS_BALANCE_FILE')
            option%io_buffer = 'FORMAT cannot be specified within &
                 &the OUTPUT,MASS_BALANCE_FILE block. Mass balance output is &
                 &written in TECPLOT format only.'
```
(`src/pflotran/output.F90:395-399`)

```fortran
          case('MASS_BALANCE_FILE')
            option%io_buffer = 'A variable list cannot be specified within &
                 &the MASS_BALANCE_FILE block. Mass balance variables are &
                 &determined internally.'
```
(`src/pflotran/output.F90:534-538`)

The column set is therefore *entirely* determined by the flow mode, the transport
mode, the coupler names, the well list, `DETAILED`, `NO_PRINT_SOURCE_SINK`, and
`TOTAL_MASS_REGIONS`. There is no way to select columns.

### Initial and final rows

`print_initial_massbal` is consumed at
`src/pflotran/simulation_subsurface.F90:471`, producing a t=0 row before the time
loop. It is **off by default**, so a `-mas.dat` typically starts at the first
scheduled output time, not at t=0.

`print_final_massbal` is set (`src/pflotran/output.F90:160`,
`src/pflotran/factory_subsurface_read.F90:1837`, `:1841`, `:1845`) and echoed to
the input record (`src/pflotran/output.F90:1476`) but a grep of all `*.F90` finds
**no site that reads it to gate an output call**. Only `print_final_snap` reaches
a waypoint (`src/pflotran/realization_subsurface.F90:1774-1777`). So `NO_FINAL`
inside `MASS_BALANCE_FILE` appears inert in this tree. Stated as a negative
finding from an exhaustive grep; not confirmed by execution.

---

## 5. Worked reading of the motivating deck

```
OUTPUT
  TIME_UNITS h
  ...
  MASS_BALANCE_FILE
    PERIODIC TIME 0.5 h
    TOTAL_MASS_REGIONS
      all
      seepage
      surface
    /
    DETAILED
  /
/
```

What this produces:

1. `pflotran-mas.dat` in the run directory
   (`src/pflotran/output_observation.F90:2430-2431`).
2. A row every 0.5 h of simulated time, via waypoints
   (`src/pflotran/init_common.F90:623-648`).
3. Header columns in order: `Time [h]`, `dt_flow [h]`, `dt_tran [h]`, the
   `Global ...` inventory family, one two-per-species block per boundary
   condition and per source/sink named after the coupler (`east`, `top_vent`,
   `top_recharge`, ...), then three `Region all ...` / `Region seepage ...` /
   `Region surface ...` blocks.
4. Rate columns carry `[kg/h]` / `[mol/h]` because `tunit = 'h'`
   (`src/pflotran/output_observation.F90:2620`, `:2724`).

### On the reported 332 columns / 32 `Global` / 93 `Region` / 68 per boundary

The total is arithmetically consistent — `3 + 32 + 93 + 3×68 = 332` — where the
three leading columns are `Time`, `dt_flow`, `dt_tran`. Both flow and transport
are active, since `dt_tran` only appears when `ntrandof > 0`
(`src/pflotran/output_observation.F90:2454`).

A per-coupler width of 68 is consistent with `2 + 2N` for a single-species
flow mode (Richards family, two water columns) plus `N = 33` printed transport
species with no active gas phase
(`src/pflotran/output_observation.F90:2617-2622` + `:2704-2731`).

However, I could **not** reconcile that `N` with the reported `Global` count of
32: for the same configuration the `Global` family is
`1 + N + n_immobile + n_gas [+ n_mineral]`
(`src/pflotran/output_observation.F90:2459-2460` + `:2528-2575`), which cannot be
32 when `N = 33`. Either the reported family counts are approximate, or some
columns were assigned to a different family when counted. **This is stated as an
unresolved discrepancy, not glossed over.**

**Do not predict the column layout — parse the header.** The header is written by
the same conditional chain as the data, so it is authoritative. The counts depend
on `naqcomp`, `print_total_mass_kg`, per-species print flags, `nactive_gas`,
`nphase`, the coupler list, the well list, and `DETAILED` — none of which are
visible in the deck alone.

---

## 6. Related files written by the same module

| Pattern | Source | Notes |
|---|---|---|
| `<prefix>-obs-<rank>.pft` | `src/pflotran/output_observation.F90:185-186` | see `observation_and_snapshot.md` |
| `<prefix>-int.dat` | `src/pflotran/output_observation.F90:2094-2097` | `INTEGRAL_FLUX`; returns immediately if no `INTEGRAL_FLUX` card (`:2069`) |
| `<prefix>-obs-<i>-agg-<j>.pft` | `src/pflotran/output_observation.F90:352-354` | `AGGREGATE_METRIC` |
| `<prefix>-obs-sec-<rank>.pft` | `src/pflotran/output_observation.F90:675-676` | secondary continuum |
