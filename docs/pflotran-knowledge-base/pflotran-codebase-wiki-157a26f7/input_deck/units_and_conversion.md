**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** the optional trailing unit token and its conversion (`units.F90`, plus the reader hooks in `input_aux.F90`)
**Last verified:** 2026-07-31

---

# Units in the Input Deck

A PFLOTRAN numeric card often accepts a **trailing unit token**:

```
INITIAL_TIMESTEP_SIZE 0.5 h
SPECIFIC_SURFACE_AREA 32000 cm^2/g
ROCK_DENSITY 2650.d0 kg/m^3
```

This document covers exactly how that token is parsed, what strings are recognized, what happens when it is omitted, and what happens when it is wrong. It is the third of three files in the `input_deck` topic; see `deck_grammar_and_reader.md` for tokenization and `conditions_regions_strata.md` for the declarative blocks.

The whole conversion engine is one 643-line file, `src/pflotran/units.F90`, with **only two public entities** (`src/pflotran/units.F90:12`):

```fortran
public :: UnitsConvertToInternal, UnitsConvertToExternal
```

There is no derived type, no registry, and no data-driven table anywhere in the file. Everything is hard-coded `select case` on string literals.

---

## 1. The grammar: `<CARD> <number> [<unit>]`

### 1.1 The optional-token mechanism

Optionality is expressed by the reader's `return_blank_error` flag plus an error-swallowing call. The canonical implementation is `InputReadAndConvertUnits` (`src/pflotran/input_aux.F90:2605-2645`):

```fortran
call InputReadWord(input,option,units,PETSC_TRUE)                   ! :2628
if (.not.InputError(input)) then
  ...
  double_value = double_value * &
                 UnitsConvertToInternal(units,internal_units_word, &
                                        keyword_string,option)      ! :2637-2639
else
  string = trim(keyword_string) // ' units'                         ! :2641
  call InputDefaultMsg(input,option,string)                         ! :2642
endif
```

Read that carefully:

- The token is requested with `return_blank_error = PETSC_TRUE`, so its absence **does** set `input%ierr`.
- `InputDefaultMsg` then prints `"<CARD> units" set to default value.` and **clears the error** (`src/pflotran/input_aux.F90:320-323`).
- When the token is absent, `double_value` is **not touched at all**.

**So omitting units is legal, produces only an informational message, and means "the number is already in the caller's internal units".**

### 1.2 The caller declares the internal units, not the deck

The second argument to `InputReadAndConvertUnits` is a string literal supplied by the *calling block reader*, not by the deck. Examples verified in this topic's scope:

| Card | Internal-units string | Site |
|---|---|---|
| `STRATA,START_TIME` | `'sec'` | `src/pflotran/strata.F90:222-225` |
| `STRATA,FINAL_TIME` | `'sec'` | `src/pflotran/strata.F90:229-232` |
| `MATERIAL_PROPERTY,ROCK_DENSITY` | `'kg/m^3'` | `src/pflotran/material.F90:379-380` |
| `TIME,INITIAL_TIMESTEP_SIZE` | `'sec'` | `src/pflotran/factory_subsurface_read.F90:2310-2313` |
| `TIME,MINIMUM_TIMESTEP_SIZE` | `'sec'` | `src/pflotran/factory_subsurface_read.F90:2317-2320` |
| `MINERAL_KINETICS,<mineral>,ACTIVATION_ENERGY` | `'J/mol'` | `src/pflotran/reaction_mineral.F90:178-180` |
| `MINERAL_KINETICS,<mineral>,SPECIFIC_SURFACE_AREA` | `'m^2/kg'` | `src/pflotran/reaction_mineral.F90:356-357` |
| `CONSTRAINT,IMMOBILE` | `'mol/m^3'` | `src/pflotran/transport_constraint_rt.F90:705` |

**There is no way to determine a card's default units from the deck.** A parser must carry a table keyed on `(block path, card)`.

### 1.3 Two exceptions to optionality

1. **Mandatory-units mode.** `input%force_units` (`src/pflotran/input_aux.F90:24`, default `PETSC_FALSE` at `:196`) makes a missing unit fatal via `InputCheckMandatoryUnits` (`:2576-2601`), message `Missing units in <block>,<card>.`
2. **Hand-rolled units cards.** Some cards read the unit token manually and call `UnitsConvertToInternal` directly, then assert with `InputErrorMsg` — making the token **mandatory**. The clearest case is `TIME,FINAL_TIME` (`src/pflotran/factory_subsurface_read.F90:2287-2296`), where the unit token is read at `:2292` and immediately asserted at `:2293`, and whose in-source comment explains why (`:2288-2289`): *"cannot use InputReadAndConvertUnits here because we need to store the units if output_option%tunit is not set"*. `TIME,SCREEN_UNITS` (`:2275-2282`) is the same shape.
3. **Deferred conversion.** `CONSTRAINT,MINERALS` stores the unit token as a *string* and converts much later (`src/pflotran/transport_constraint_rt.F90:551-558`, comment at `:550`), with a default of `'m^2/m^3'` when absent. See §7.

---

## 2. How a unit string is parsed

Parsing is a **three-level character split**. There is no tokenizer, no exponent arithmetic, and no lookup table.

### Level 0 — `|` splits *alternative internal units* (never the user's string)

`UnitsConvertToInternal` (`src/pflotran/units.F90:18-92`) loops over `|`-separated alternatives of the **internal** units string, trying each left to right and stopping at the first that parses (`:57-75`):

```fortran
do while(ind_or /= 0)
  length = len_trim(internal_units_buff1)              ! :58
  ind_or = index(trim(internal_units_buff1),"|")       ! :59
  if (ind_or == 0) then
    call UnitsConvertParse(units_buff,internal_units_buff1, &
                           conversion_factor,error,error_msg)   ! :61-62
    if (.not.error) successful = PETSC_TRUE            ! :63
    if (successful) exit                               ! :64
  else
    internal_units_buff2 = internal_units_buff1(1:(ind_or-1))   ! :68
    call UnitsConvertParse(units_buff,internal_units_buff2, &
                           conversion_factor,error,error_msg)   ! :69-70
    if (.not.error) successful = PETSC_TRUE            ! :71
    if (successful) exit                               ! :72
    internal_units_buff1 = internal_units_buff1((ind_or+1):length)  ! :73
  endif
enddo
```

This is how a card accepts dimensionally different but equivalent spellings, e.g. `'MJ/sec|MW'` (`src/pflotran/condition.F90:1268`) or `'MW|MJ/sec'` (`:1283`). **The user's own string is never split on `|`.**

### Level 1 — `/` splits numerator from denominator

`UnitsConvertParse` (`src/pflotran/units.F90:96-191`):

```fortran
length = len(units)                        ! :136   <-- len, not len_trim
ind = index(trim(units),"/")               ! :137
if (ind == 0) then
  numerator_units = trim(units)            ! :140
else
  numerator_units = units(1:(ind-1))       ! :144
  denominator_units = units((ind+1):length)! :145
endif
```

**Only the first `/` is honoured.** `a/b/c` puts `b/c` in the denominator, which then fails, because `/` is not a Level-2 delimiter.

A structural mismatch — one side has a denominator and the other does not — is an error before any numeric work (`:161-176`), with two distinct messages (`:163-166`, `:170-173`). The final combination is a single division (`:189`):

```fortran
units_conversion = numerator_conv_factor/denominator_conv_factor
```

### Level 2 — `-` splits a product of **at most three** factors

`UnitsConvert` (`src/pflotran/units.F90:195-323`) splits each side on `-` into up to three slots (user side `:242-258`, internal side `:269-285`), with a hard cap enforced at `:252-257` and `:280-282`: *"Maximum number of user units exceeded. Unit numerators or denominators are limited to a maximum of 3 units each."*

Unused slots hold the sentinel `'not_assigned'` (`:237-238`, `:264-265`).

**There is NO split on `^`.** The caret is part of the literal token: `'m^2'`, `'cm^3'`, `'dm^3'`, `'km^2'` are matched verbatim as whole strings (`src/pflotran/units.F90:352`, `:355`). Nothing is derived by exponentiation, so `m^4`, `s^-1`, and `cm^3/s^2` are **not** recognized.

### Level 3 — dimensional check, then conversion via SI

Each token is categorized (`UnitsCategory`, `src/pflotran/units.F90:327-395`), the two category triples are compared **order-insensitively** (`UnitsCategoryCheck`, `:559-616`, matching loop `:587-601`), each side is converted to SI (`UnitsConvertToSI`, `:399-555`), and the ratio is returned (`:321`):

```fortran
units_conversion = conv_user_to_SI / conv_internal_to_SI
```

Order-insensitivity means `kg-m/s` and `m-kg/s` are interchangeable.

### Worked traces

| User string | Split | Result |
|---|---|---|
| `h` | no `/`, no `-`; one token `'h'` | time, `3600.d0` (`src/pflotran/units.F90:465-466`) |
| `m/yr` | numerator `m`, denominator `yr` | `1.d0 / 3.1536d7` |
| `cm^2/g` | numerator `'cm^2'` (area, `1.d-4`, `:441-442`), denominator `'g'` (mass, `1.d-3`, `:510-511`) | `1.d-4 / 1.d-3` |
| `kg/m^3` | `'kg'` (`1.d0`, `:512-513`) over `'m^3'` (`1.d0`, `:429-430`) | `1.d0` |
| `MJ/m^2-sec` | denominator `-`-split into `m^2` and `sec` | matches internal `'MW/m^2|MJ/m^2-sec'` on the second alternative |

---

## 3. Recognized unit literals — the dimension table

`UnitsCategory`, `select case(trim(unit(k)))` at `src/pflotran/units.F90:351`.

| Category | Literals (verbatim) | Line |
|---|---|---|
| `volume` | `'cm^3','l','L','ml','mL','dm^3','m^3','gal','gallon','bbl','cf','Mcf'` | `:352-354` |
| `area` | `'cm^2','dm^2','m^2','km^2'` | `:355-356` |
| `length` | `'km','m','met','meter','dm','cm','mm'` | `:357-358` |
| `time` | `'s','sec','second','min','minute','h','hr','hour','d','day','w','week','mo','month','y','yr','year'` | `:359-361` |
| `viscosity` | `'Pa.s','cP','centiPoise','Poise','P'` | `:362-363` |
| `energy` | `'J','kJ','MJ','cal','kcal'` | `:364-365` |
| `power` | `'W','kW','MW'` | `:366-367` |
| `molar_mass` | `'mol','mole','moles','kmol'` | `:368-369` |
| `mass` | `'ug','mg','g','kg'` | `:370-371` |
| `temperature` | `'C','Celcius'` *(sic, misspelled)* | `:372-373` |
| `temperature` **+ fatal** | `'K','Kelvin'` | `:374-377` |
| `pressure` | `'Pa','kPa','MPa','Bar','psi','atm'` | `:378-379` |
| `concentration` | `'M','mM'` | `:380-381` |
| `force` | `'N'` | `:382-383` |
| `unitless` | `'unitless','1'` | `:384-385` |
| `not_assigned` | `'not_assigned'` | `:386-387` |
| — | `case default` → error | `:388-390` |

There is **no** `density`, `velocity`, `flux`, `permeability`, or `conductivity` category. Compound dimensions exist only as `-` / `/` combinations of the above.

---

## 4. Conversion factors — the SI table

`UnitsConvertToSI`, `select case(trim(unit))` at `src/pflotran/units.F90:423`. The comment banners give PFLOTRAN's SI pivot per dimension.

**Volume → `meter^3`** (`:424`)

| Literal(s) | Factor | Line |
|---|---|---|
| `'cm^3','mL'` | `1.d-6` | `:425-426` |
| `'L','dm^3'` | `1.d-3` | `:427-428` |
| `'m^3'` | `1.d0` | `:429-430` |
| `'gal','gallon'` | `3.785411784d-3` | `:431-432` |
| `'cf'` | `0.02831685` | `:433-434` |
| `'Mcf'` | `0.02831685d3` (comment: *"In Field units M means 1000"*) | `:435-436` |
| `'bbl'` | `0.1589873141` | `:437-438` |
| `''` | *(no assignment; falls through with the `1.d0` default from `:416`)* | `:439` |

**Area → `meter^2`** (`:440`): `'cm^2'` `1.d-4` (`:441-442`), `'dm^2'` `1.d-2` (`:443-444`), `'m^2'` `1.d0` (`:445-446`), `'km^2'` `1.d6` (`:447-448`).

**Length → `meter`** (`:449`): `'km'` `1000.d0` (`:450-451`), `'m','meter'` `1.d0` (`:452-453`), `'dm'` `1.d-1` (`:454-455`), `'cm'` `1.d-2` (`:456-457`), `'mm'` `1.d-3` (`:458-459`).

**Time → `second`** (`:460`)

| Literal(s) | Factor | Line |
|---|---|---|
| `'s','sec','second'` | `1.d0` | `:461-462` |
| `'min','minute'` | `60.d0` | `:463-464` |
| `'h','hr','hour'` | `3600.d0` | `:465-466` |
| `'d','day'` | `24.d0*3600.d0` = 86 400 | `:467-468` |
| `'w','week'` | `7.d0*24.d0*3600.d0` = 604 800 | `:469-470` |
| `'mo','month'` | `DAYS_PER_YEAR/12.d0*24.d0*3600.d0` = 2 628 000 | `:471-472` |
| `'y','yr','year'` | `DAYS_PER_YEAR*24.d0*3600.d0` = 3.1536e7 | `:473-474` |

`DAYS_PER_YEAR = 365.d0` (`src/pflotran/pflotran_constants.F90:73`) — **PFLOTRAN's year is exactly 365 days, not a Julian or tropical year.** A commented-out `365.24224537d0` sits at `src/pflotran/pflotran_constants.F90:75`.

**Viscosity → `Pascal-second`** (`:475`): `'Pa.s'` `1.0` (`:476-477`), `'cP','centiPoise'` `1.d-3` (`:478-479`), `'P','Poise'` `1.d-1` (`:480-481`).

**Energy → `Joule`** (`:482`): `'J'` `1.d0` (`:483-484`), `'kJ'` `1.d3` (`:485-486`), `'MJ'` `1.d6` (`:487-488`), `'cal'` `4.184d0` (`:489-490`), `'kcal'` `4.184d3` (`:491-492`).

**Power → `Watt`** (`:493`): `'W'` `1.d0` (`:494-495`), `'kW'` `1.d3` (`:496-497`), `'MW'` `1.d6` (`:498-499`).

**Amount → `mole`** (`:500`, category confusingly named `molar_mass`): `'mol','mole','moles'` `1.d0` (`:501-502`), `'kmol'` `1.d3` (`:503-504`).

**Mass → `kilogram`** (`:505`): `'ug'` `1.d-9` (`:506-507`), `'mg'` `1.d-6` (`:508-509`), `'g'` `1.d-3` (`:510-511`), `'kg'` `1.d0` (`:512-513`).

**Temperature → `C`** (`:514`): `'C','Celsius'` `1.d0` (`:515-516`).

**Pressure → `Pascal`** (`:517`): `'Pa'` `1.d0` (`:518-519`), `'kPa'` `1.d3` (`:520-521`), `'MPa'` `1.d6` (`:522-523`), `'Bar'` `1.d5` (`:524-525`), `'psi'` `6894.757` (`:526-527`), `'atm'` `101325.d0` (`:528-529`).

**Concentration → `M`** (`:530`): `'M'` `1.d0` (`:531-532`), `'mM'` `1.d-3` (`:533-534`).

**Force → `Newton`** (`:535`): `'N'` `1.d0` (`:536-537`).

**Unitless → `1`** (`:538`): `'unitless','1'` `1.d0` (`:539-540`).

The source itself flags what is untested (`src/pflotran/units.F90:419-421`):

```
! units not covered by regression tests
! gal, gallon, cf, Mcf, bbl, km^2,
! month, Pa.s, cP, P, Poise, kcal, mole, moles, ug, Celsius, N
```

### 4.1 Units that do **not** exist

Stated explicitly, because their absence is what a parser will trip over:

- **Time:** no `ms`, `us`, `ns`, `ka`, `Ma`, `kyr`, `Myr`. No plural forms (`days`, `yrs`, `years`, `secs`, `hrs`) — the only plural anywhere is `'moles'`.
- **Mass:** no `ng`, `t`, `tonne`, `lb`.
- **Amount:** no `mmol`, `umol`, `nmol`.
- **Pressure:** no `GPa`, `mbar`, `torr`, `mmHg`. Lowercase `bar` is **not** accepted, only `Bar`.
- **Concentration:** no `uM`, `nM`, `ppm`, `molal`, `molality`.
- **Temperature:** Kelvin is explicitly rejected (§5).

---

## 5. Temperature: multiplicative only, and Celsius is internal

**There is no additive offset anywhere in `units.F90`.** The entire algebra is products and two divisions (`src/pflotran/units.F90:305`, `:315`, `:321`, `:189`).

`'C','Celsius'` maps to `1.d0` under the banner `! ---> TEMPERATURE ---> (C)` (`src/pflotran/units.F90:514-516`), so **PFLOTRAN's internal temperature unit is degrees Celsius, not Kelvin.** This is the one place the module's "SI" pivot is deliberately non-SI (the other is concentration, which pivots on molarity M = mol/L, `:530`).

Kelvin is therefore forbidden rather than offset-converted (`src/pflotran/units.F90:374-377`):

```fortran
case('K','Kelvin')
  unit_category(k) = 'temperature'
  error_msg = 'Kelvin temperature units are not supported. Use Celcius.'
  error = PETSC_TRUE
```

(The error message itself misspells "Celsius".) Any C↔K conversion must be done by the caller.

**Caveat.** `FLOW_CONDITION`'s own `UNITS` card *does* accept the token `K` (`src/pflotran/condition.F90:1181-1182`), because that card is a separate hard-coded list that never reaches `units.F90` at parse time. Whether such a value is later converted correctly was not traced.

---

## 6. Case sensitivity

**Unit strings are case-sensitive, with no folding of any kind.**

`units.F90` contains **no** `StringToUpper`, no `StringToLower`, no `StringCompare`, and does not even `use String_module`. The only string operations are `trim`, `len`, `len_trim`, `index`, and substring slicing. Both dispatch points are exact-match `select case` on a trimmed string (`src/pflotran/units.F90:351`, `:423`).

Case is **semantically load-bearing**:

| Pair | Meaning |
|---|---|
| `M` vs `m` | molar vs metre (`:531` vs `:452`) |
| `L` vs `l` | litre works; lowercase does not reach a factor (§6.1) |
| `Bar` vs `bar` | `Bar` works (`:524`); `bar` errors |
| `MJ`/`kJ`, `MW`/`kW`, `MPa`/`kPa`, `Mcf` | SI prefix casing must be exact |
| `C` vs `cal`/`cm` | Celsius vs calorie vs centimetre |

The only concession to variation is the explicit alias lists inside each `case` (`'s','sec','second'`, `'y','yr','year'`, and so on).

### 6.1 Table-disagreement defects

`UnitsCategory` and `UnitsConvertToSI` are two independent tables that must agree. They do not, in four places. A token in the first but not the second passes categorization and then dies in `UnitsConvertToSI`'s `case default` (`src/pflotran/units.F90:547`).

| Token | In `UnitsCategory` | In `UnitsConvertToSI` | Net effect |
|---|---|---|---|
| `'l'`, `'ml'` | yes (`:352`) | **no** (only `'L'` `:427`, `'mL'` `:425`) | fails at `:547` |
| `'met'` | yes (`:357`) | **no** (only `'m','meter'` `:452`) | fails at `:547` |
| `'Celcius'` | yes, misspelled (`:372`) | **no** (has `'Celsius'` `:515`) | fails at `:547` |
| `'Celsius'` | **no** (`:372` has the misspelling) | yes (`:515`) | fails at `:388` |
| `'unknown'` | **no** | yes (`:542`) | fails at `:388` before reaching `:542` |
| `''` (empty) | **no** | yes, silently `1.d0` (`:439`) | fails at `:388`, since categorization runs first (`:291` before `:303`) |

**Net: neither `Celcius` nor `Celsius` works.** Only the single letter `C` converts end to end.

---

## 7. Deferred and special-cased units

Not every unit token reaches `units.F90` immediately.

**`CONSTRAINT,MINERALS` specific surface area** stores the raw token and converts later (`src/pflotran/transport_constraint_rt.F90:551-558`; comment at `:550`: *"read units if they exist. conversion takes place later"*). The default when absent is the literal `'m^2/m^3'` (`:554`).

The deferred interpretation, in `ReactionMnrlProcessConstraint` (`src/pflotran/reaction_mineral.F90:894`), lowercases the token (`:996`) and matches on **suffix**, not on the whole string (`:997-1011`):

| Suffix | Basis | Internal units |
|---|---|---|
| `…m^3_mnrl` | per mineral volume | `'m^2/m^3'` |
| `…g` | per mineral **mass** | `'m^2/kg'` |
| `…m^3` | per **bulk** volume | bulk-volume basis |

Anything else is fatal (`:1008-1010`). This is why `32000 cm^2/g` on a mineral row means area **per unit mineral mass** while a bare `5.2d2` means area per unit mineral volume — a factor that depends on mineral density, not a units conversion.

**`FLOW_CONDITION`'s `UNITS` card** (`src/pflotran/condition.F90:1162-1191`) is a *separate, narrower* hard-coded list that sets block-level defaults without calling `units.F90`. Its spellings differ from `units.F90`'s in two visible ways: it accepts `KPa` (`:1171`) where `units.F90` has `kPa` (`src/pflotran/units.F90:520`), and it accepts `hr` but not `h` or `hour` (`src/pflotran/condition.F90:1167`). See `conditions_regions_strata.md` §7.2 for the full list.

---

## 8. Failure modes and their messages

Six distinct errors, all propagated as an `error_msg` string that surfaces in `UnitsConvertToInternal` (`src/pflotran/units.F90:77-88`):

```fortran
if (.not.successful) then
  if (present(ierr)) then
    ierr = -1
    return                                                        ! :80
  else
    option%io_buffer = NL // 'Location of units conversion error: ' // &
                       trim(keyword_string)                       ! :82-83
    call PrintMsg(option)
    option%io_buffer = error_msg
    call PrintErrMsg(option)                                      ! :86  fatal
  endif
endif
```

| # | Condition | Message | Line |
|---|---|---|---|
| 1 | token not in the dimension table | `The given units are unrecognized: <unit>` | `:389` |
| 2 | token not in the SI table | `Unit [ <unit> ] not recognized when converting to SI units. If this is not a spelling error, then the unit is not supported.` | `:548-550` |
| 3 | sentinel reached SI conversion | `Unit not assigned or unknown. Please e-mail pflotran-dev@googlegroups.com (attn: jmfrede) with your input file and screen output.` | `:543-545` |
| 4 | numerator/denominator structure mismatch | `Units provided do not match the expected unit structure (numerator/denominator). A unit denominator was expected, but was not given: <units>` / `… was not expected, but was given: <units>` | `:163-166`, `:170-173` |
| 5 | dimensional mismatch | `Mismatch between the category of the given units and the expected, internal units. Units of [<internal>] were expected, but units of [<user>] were given.` | `:606-609` |
| 6 | more than three `-`-separated factors | `Maximum number of user units exceeded. Unit numerators or denominators are limited to a maximum of 3 units each.` (and the internal-units twin) | `:253-255`, `:280-282` |

Plus the Kelvin rejection at `:376` (§5).

**Two diagnostics traps worth knowing:**

- With `|`-separated alternative internal units, `error_msg` holds the message from the **last** alternative tried, which may name a form the user never wrote (`:57-75`).
- When the optional `ierr` argument is supplied, failure returns `ierr = -1` and the function value is the `1.d0` set at `:52`, because the assignment at `:90` is skipped. **A caller that ignores `ierr` silently gets a conversion factor of 1.**

`UnitsConvertToExternal` (`:620-641`) is a one-line reciprocal (`:638-639`) that **omits `ierr`**, so every failure on the output path is fatal.

---

## 9. Defects found by reading (cite-ready, not runtime-observed)

1. **Out-of-bounds write on more than three `-`-separated factors.** In `src/pflotran/units.F90:242-258`, the bounds check `if (k > 3)` at `:252` fires *after* `k` is incremented at `:251`, but the `do while` condition at `:242` tests only `ind_dash /= 0`, and the `if (error) return` guard sits at `:259`, **after** the loop. For `a-b-c-d` the loop re-enters with `k = 4` and writes `unit_user(k)` at `:246`/`:248` against an array declared `unit_user(3)` at `:215`. The internal-units loop has the identical shape (`:269-285`, declaration `:218`, guard `:286`).
2. **Silent truncation at 32 characters.** `units_buff` and `internal_units_buff1/2` are `MAXSTRINGLENGTH` = 512 (`:38-40`) but `UnitsConvertParse`'s dummies are `MAXWORDLENGTH` = 32 (`:111`), as are `UnitsConvert`'s (`:208-209`). Constants at `src/pflotran/pflotran_constants.F90:33-34`.
3. **`len` versus `len_trim` asymmetry** at `:136` (user) versus `:148` (internal), so `denominator_units` carries trailing blanks until `trim` at `:236`/`:244`.
4. **Misleading category-mismatch message.** `UnitsCategoryCheck` matches order-insensitively (`:587-601`) but reports `unit_internal_cat(k)` and `unit_user_cat(k)` for the same `k` (`:608-609`), which need not be the pair that actually failed.
5. **Single-precision literals in a double-precision table** — `0.02831685` (`:434`), `0.1589873141` (`:438`), `1.0` (`:477`), `6894.757` (`:527`) lack `d0` exponents and carry only ~7 significant digits.
6. **`error` is not initialized** in `UnitsConvertToInternal` before the loop at `:57`; it is only ever set inside `UnitsConvertParse` (`:125`). Safe in practice because the call at `:61`/`:69` always precedes the test at `:63`/`:71`.

---

## 10. Checklist for a parser touching a units-bearing value

1. **Never rewrite a number without checking the next token.** If it is a recognized unit literal (§3), it is part of the value and must be preserved or updated consistently.
2. **Do not normalize case.** `M` is not `m`, `Bar` is not `bar` (§6).
3. **Do not synthesize a unit token** where the deck omitted one — omission means "already internal", and the internal units are card-specific (§1.2).
4. **Treat `cm^2/g` on a `MINERALS` row as a basis change, not a scale factor** (§7).
5. **Assume a 365-day year** when converting `yr` (§4).
6. **Assume Celsius** for temperature, and never emit `K` into a `units.F90` path (§5).
7. **Do not emit more than three `-`-joined factors** on either side of a `/`, or more than one `/` (§2, §9.1).

---

## 11. Things not established from static reading

- **Whether `FLOW_CONDITION`'s `UNITS` card values (`K`, `KPa`, `hr`) are later routed through `units.F90`** — and if so, whether `K` and `KPa` fail there. The card's own list (`src/pflotran/condition.F90:1167-1186`) accepts strings that `units.F90` rejects, but the downstream path was not traced end to end.
- **Whether `input%force_units` is ever set true.** It is initialized `PETSC_FALSE` at `src/pflotran/input_aux.F90:196`; no card that sets it was found within this topic's scope.
- **The out-of-bounds write in §9.1** is derived from reading the loop structure; it was not reproduced by running PFLOTRAN.
- **Whether the untested-units list at `src/pflotran/units.F90:419-421` is still accurate** at this commit. It is a hand-maintained comment, not generated.
