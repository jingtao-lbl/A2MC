**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** declarative blocks and name-based linkage — `CONSTRAINT`, `REGION`, `STRATA`, `FLOW_CONDITION`; positional data rows; dynamic-key blocks
**Last verified:** 2026-07-31

---

# Declarative Blocks, Positional Rows, and Name Linkage

This is the companion to `deck_grammar_and_reader.md`. That file covers *how* the deck is tokenized and blocked. This file covers the block shapes that a parser must recognize by name, and the two grammar productions that break the "keyword then value" pattern:

- **dynamic-key blocks**, where the block key is user data rather than a keyword (§4);
- **positional data rows**, where a line is a label plus unlabelled columns (§5).

Everything here is cited to source at commit `157a26f7`.

---

## 1. The declare-then-reference architecture

PFLOTRAN's deck is **declarative with late binding**. Blocks declare named objects; other blocks reference them by string; and the strings are not resolved until reading is complete.

```
REGION <name>            ─┐
MATERIAL_PROPERTY <name>  ├── declaration phase: create object, store name
CONSTRAINT <name>         │   (during factory_subsurface_read.F90's SUBSURFACE loop)
FLOW_CONDITION <name>    ─┘
                             ↓
STRATA / BOUNDARY_CONDITION / INITIAL_CONDITION / ...
    store *strings*: region_name, material_property_name, ...
                             ↓
patch.F90::PatchProcessCouplers  ── resolution phase: string → pointer
```

Three consequences a parser must internalize:

1. **Declaration order in the file is irrelevant.** A `STRATA` may reference a `REGION` declared 500 lines later.
2. **A typo in a name is not a syntax error.** It is a *link* error, reported much later with a different message shape (§6).
3. **Names are stored verbatim, case-sensitively.** Card *keywords* are usually upper-cased before dispatch, but the name arguments are not (§2.1).

---

## 2. `REGION` — geometry declaration

### 2.1 Block shape and the name argument

The block is opened and *named* by the top-level `SUBSURFACE` dispatcher, then the body is delegated (`src/pflotran/factory_subsurface_read.F90:1187-1196`):

```fortran
case ('REGION')
  region => RegionCreate()                                        ! :1188
  call InputReadWord(input,option,region%name,PETSC_TRUE)         ! :1189  <-- the name
  call InputErrorMsg(input,option,'name','REGION')                ! :1190
  call PrintMsg(option,region%name)                               ! :1191
  call RegionRead(region,input,option)                            ! :1192
  ...
  call RegionAddToList(region,realization%region_list)            ! :1195
```

So the deck form is `REGION <name>` on the opening line, body on following lines, closed by `/` or `END`.

`region%name` is `character(len=MAXWORDLENGTH)` (`src/pflotran/region.F90:33`), i.e. **32 characters max**. The name is read with `return_blank_error = PETSC_TRUE`, so omitting it is fatal. **No `StringToUpper` is applied to the name** — region names are case-sensitive.

`RegionRead` is `src/pflotran/region.F90:400-599`, with the standard block loop: `InputPushBlock` (`:423`), fetch (`:426`), error exit (`:427`), terminator exit (`:428`), card read (`:430`), **`StringToUpper(keyword)` (`:432`)** — so REGION *cards* are case-insensitive — dispatch (`:434`), `case default` → `InputKeywordUnrecognized(...,'REGION',...)` (`:593-594`), `InputPopBlock` (`:597`).

### 2.2 Card catalogue

| Card | Line | Payload |
|---|---|---|
| `BLOCK` | `src/pflotran/region.F90:436` | 6 integers `i1 i2 j1 j2 k1 k2` (`:438`, `:446`, `:448`, `:450`, `:452`, `:454`), with a fallback to the *next* line if the first is absent (`:439-444`) |
| `CARTESIAN_BOUNDARY` | `:456` | one face name (§2.4) |
| `COORDINATE` | `:479` | 3 doubles `x y z` (`:482`, `:490`, `:492`), same next-line fallback (`:483-488`) |
| `COORDINATES` | `:494` | sub-block of positional `x y z` rows (§5.4) |
| `INFINITE` | `:498` | bare flag; hard-codes coordinates `±1.d20` (`:501-506`) |
| `POLYGON` | `:507` | pushed sub-block (§2.3) |
| `FILE` | `:550` | one filename (`:551`); the *format* is chosen later by extension (§2.5) |
| `LIST` | `:553` | sub-block of positional integer rows (§5.5) |
| `FACE` | `:571` | one face name (§2.4) |

**There is no units conversion anywhere in `region.F90`** — no `InputReadAndConvertUnits`, no `UnitsConvert*` call, and no `UNITS` card. Coordinates are bare doubles and are implicitly metres; the only evidence of that convention is the input-record writer appending `' m'` (`src/pflotran/region.F90:1371`, `:1378`, `:1385`). **A parser must not accept a trailing unit token after REGION coordinates.**

### 2.3 The `POLYGON` sub-block

`src/pflotran/region.F90:507-549`, pushed at `:512`, popped at `:549`.

| Sub-card | Line | Payload |
|---|---|---|
| `TYPE` | `:521` | one word: `BOUNDARY_FACES_IN_VOLUME` (`:526`) or `CELL_CENTERS_IN_VOLUME` (`:528`); anything else fatal (`:530-533`) |
| `XY` | `:535` | positional coordinate rows into `xy_coordinates` (`:536-537`) |
| `XZ` | `:538` | ditto `xz_coordinates` (`:539-540`) |
| `YZ` | `:541` | ditto `yz_coordinates` (`:542-543`) |

**Quirk worth flagging:** the `XY`/`XZ`/`YZ` vertex rows still carry **three** numbers, not two, because they go through the same `GeometryReadCoordinate` that unconditionally reads x, y, and z (`src/pflotran/geometry.F90:190-195`).

### 2.4 Face names

`CARTESIAN_BOUNDARY` (`src/pflotran/region.F90:461-478`) and `FACE` (`:575-592`) use two **duplicated, identical** mapping tables. Constants come from `src/pflotran/grid_structured.F90:14-19`.

| Deck literal | `CARTESIAN_BOUNDARY` line | `FACE` line | Constant | Value |
|---|---|---|---|---|
| `WEST` | `:462` | `:576` | `WEST_FACE` | 1 |
| `EAST` | `:464` | `:578` | `EAST_FACE` | 2 |
| `NORTH` | `:466` | `:580` | `NORTH_FACE` | 4 |
| `SOUTH` | `:468` | `:582` | `SOUTH_FACE` | 3 |
| `BOTTOM` | `:470` | `:584` | `BOTTOM_FACE` | 5 |
| `TOP` | `:472` | `:586` | `TOP_FACE` | 6 |

Note the source order (`WEST, EAST, NORTH, SOUTH, …`) is **not** the numeric order, because `SOUTH_FACE = 3` and `NORTH_FACE = 4` (`src/pflotran/grid_structured.F90:16-17`). Both tables upper-case the word first (`:460`, `:574`), so face names are case-insensitive.

The two `case default` messages differ: `'Cartesian boundary face "<w>" not recognized.'` (`:475-476`) versus `'FACE "<w>" not recognized.'` (`:588-589`).

**These six literals are exhaustive.** There is no `UP`, `DOWN`, `XMIN`, `XMAX`, `ZMIN`, `ZMAX`, `FRONT`, or `BACK`, and a numeric face id is not accepted here (numeric face ids appear only as column 2 of a `LIST` row, §5.5).

### 2.5 `REGION ... FILE` — format chosen by extension, after reading

`FILE` stores only a filename (`src/pflotran/region.F90:551`). The actual format dispatch happens after the whole deck is read, in `InitCommonReadRegionFiles` (`src/pflotran/init_common.F90:208-275`), guarded by `if (len_trim(region%filename) > 1)` (`:236`):

| Extension test | Line | Handler |
|---|---|---|
| `.h5` | `src/pflotran/init_common.F90:237` | HDF5 region readers (`:238-253`); requires a `Cell Ids` / `Face Ids` / `Vertex Ids` dataset, else fatal (`:245-246`) |
| `.ss` | `:255` | sideset reader, `def_type = DEFINED_BY_SIDESET_UGRID` (`:256`) |
| `.ex` | `:260` | explicit-faceset reader, `def_type = DEFINED_BY_FACE_UGRID_EXP` (`:261`) |
| otherwise | `:268` | plain ASCII cell-id list |

**`.ss` file grammar** (`RegionReadSideSet`, `src/pflotran/region.F90:833-990`, documented in-source at `:870-881`): line 1 is the face count (`:890`); each subsequent row is `<type> <v1> <v2> ...` where the type token (`:921`) maps `Q` → 4 vertices (`:925-926`), `T` → 3 (`:927-928`), `L` → 2 (`:929-930`). The `case default` error message advertises only `Q` and `T` (`:932-934`) even though `L` is accepted — a documentation defect in the source itself.

**`.ex` file grammar** (`RegionReadExplicitFaceSet`, `src/pflotran/region.F90:994-1096`, documented at `:1025-1041`): one card, `CONNECTIONS` (`:1053`), which reads a count (`:1056`) then exactly that many positional rows of **`cell_id  x  y  z  area`** (`:1072`, `:1074`, `:1077`, `:1080`, `:1083`).

**Known-broken path:** the plain-ASCII reader's `> 2 columns` branch (`src/pflotran/region.F90:711-798`) composes a diagnostic telling the user to switch to `.ss`/`.ex` (`:712-715`) but its `PrintErrMsg` is **commented out** at `:716`, and it then reads from `temp_int_array`, which was zeroed at `:682` and never filled. Treat more than two columns in a plain region file as unsupported.

---

## 3. `STRATA` — material-to-region association

### 3.1 Block shape — no name, two spellings

`src/pflotran/factory_subsurface_read.F90:1354-1357`:

```fortran
case ('STRATIGRAPHY','STRATA')
  strata => StrataCreate()
  call StrataRead(strata,input,option)
  call RealizationAddStrata(realization%patch,strata)
```

**`STRATA` takes no name argument** — there is no `InputReadWord` between the `case` and the `StrataRead` call, and `strata_type` has **no `name` field at all** (`src/pflotran/strata.F90:18-35`). Its only identity is `strata%id`, assigned by insertion order (`src/pflotran/strata.F90:285`). Any trailing token on the `STRATA` line is silently discarded.

`STRATIGRAPHY` is a full alias, though every error string inside the reader says `'STRATA'` (`src/pflotran/strata.F90:196`, `:202`, `:205`, `:209`, `:212`, `:238`).

### 3.2 Two reader deviations that matter to a parser

`StrataRead` (`src/pflotran/strata.F90:166-267`) departs from the canonical block loop in two ways, both verified by reading the whole routine:

1. **No case folding.** There is **no `StringToUpper` call anywhere in `strata.F90`** (zero occurrences in the file). `String_module` is imported (`:175`) but never used for folding. Contrast `RegionRead`, which folds at `src/pflotran/region.F90:432`. **STRATA cards must be uppercase.**
2. **No `InputError` check after the line fetch.** The loop is fetch (`:191`) → terminator test (`:193`) → card read (`:195`), with no `if (InputError(input)) exit` between them, unlike `src/pflotran/region.F90:427`. An unterminated `STRATA` block at EOF does not exit cleanly here.

### 3.3 Card catalogue

| Card | Line | Payload | Units |
|---|---|---|---|
| `FILE` | `src/pflotran/strata.F90:200` | filename → `material_property_filename` | — |
| `REGION` | `:203` | word → `region_name` | — |
| `MATERIAL` | `:206` | word → `material_property_name` | — |
| `SURFACE_DATASET` | `:210` | word → `dataset_name` | — |
| `SET_MATERIAL_IDS_BELOW_SURFACE` | `:213` | bare flag | — |
| `SET_MATERIAL_IDS_ABOVE_SURFACE` | `:215` | bare flag | — |
| `REALIZATION_DEPENDENT` | `:217` | bare flag | — |
| `START_TIME` | `:219` | double (`:220`) | **optional trailing unit**, internal `'sec'` (`:222-225`) |
| `FINAL_TIME` | `:226` | double (`:227`) | **optional trailing unit**, internal `'sec'` (`:229-232`) |
| `WELL` | `:233` | bare flag | — |
| `INACTIVE` | `:235` | bare flag | — |

**`STRATA` has no nested sub-blocks.** The only `InputPushBlock` is the outer one at `:188`. Every card is a single line.

### 3.4 Post-block semantic validation

Three rules enforced after the block closes, which a parser should mirror as lint checks:

1. A `MATERIAL` with neither `REGION` nor `SURFACE_DATASET` is fatal (`src/pflotran/strata.F90:244-252`): *"The MATERIAL property "…" must have an associated REGION or SURFACE_DATASET in the STRATA block. Otherwise, please use "FILE <filename>" to read material IDs from a file."*
2. `START_TIME` and `FINAL_TIME` must appear together; either alone is fatal (`:254-262`).
3. Setting `START_TIME` globally switches on transient porosity: `if (Initialized(strata%start_time)) option%flow%transient_porosity = PETSC_TRUE` (`:263-265`). **A time card in one `STRATA` block silently changes model physics for the whole run.**

---

## 4. Dynamic-key blocks — when the key is data

> **Question.** Inside `MINERAL_KINETICS`, each mineral NAME opens a sub-block — the key is data, not a keyword. Find that loop. Which other blocks behave this way?

**CONFIRMED.** The loop is `ReactionMnrlReadKinetics` (`src/pflotran/reaction_mineral.F90:84-529`).

### 4.1 The `MINERAL_KINETICS` read loop

```fortran
call InputPushBlock(input,'MINERAL_KINETICS',option)          ! reaction_mineral.F90:128
do
  call InputReadPflotranString(input,option)                  ! :131
  if (InputError(input)) exit                                 ! :132
  if (InputCheckExit(input,option)) exit                      ! :133

  call InputReadWord(input,option,name,PETSC_TRUE)            ! :135  <-- THE DYNAMIC KEY
  call InputErrorMsg(input,option,'mineral name', &
                     'CHEMISTRY,MINERAL_KINETICS')            ! :136-137

  cur_mineral => mineral%mineral_list                         ! :139
  found = PETSC_FALSE
  do
    if (.not.associated(cur_mineral)) exit
    if (StringCompare(cur_mineral%name,name,MAXWORDLENGTH)) then   ! :143
      found = PETSC_TRUE
      ...
      call InputPushBlock(input,name,option)                  ! :149  <-- block named BY DATA
      do
        call InputReadPflotranString(input,option)            ! :151
        call InputReadStringErrorMsg(input,option,error_string)
        if (InputCheckExit(input,option)) exit                ! :153
        call InputReadCard(input,option,keyword)              ! :154
        error_string = 'CHEMISTRY,MINERAL_KINETICS,'//name    ! :155
        ...
        select case(trim(keyword))                            ! :158
```

Two details make this unambiguous:

- The first token of each row is read as **data** (`name`) and never reaches a `select case`.
- `InputPushBlock` is called with the *data value* as the block label (`:149`), so the breadcrumb in error messages shows the mineral name. The error-string prefix is composed the same way (`:155`).

An unrecognized mineral name is fatal, but only after the whole mineral list has been searched (`src/pflotran/reaction_mineral.F90:497-501`): *"Mineral "…" specified under CHEMISTRY,MINERAL_KINETICS not found in list of available minerals."* So the key must have been declared earlier in a `MINERALS` block.

**Cards valid inside a per-mineral sub-block** (verbatim, complete, from `src/pflotran/reaction_mineral.F90`):

| Card | Line |
|---|---|
| `RATE_CONSTANT`, `PRECIPITATION_RATE_CONSTANT`, `DISSOLUTION_RATE_CONSTANT` | `:159-160` |
| `ACTIVATION_ENERGY` | `:174` (units `'J/mol'`, `:178-180`) |
| `AFFINITY_THRESHOLD` | `:181` |
| `AFFINITY_POWER` | `:185` |
| `MINERAL_SCALE_FACTOR` | `:189` |
| `TEMKIN_CONSTANT` | `:193` |
| `SURFACE_AREA_POROSITY_POWER` | `:197` |
| `SURFACE_AREA_VOL_FRAC_POWER` | `:200` |
| `RATE_LIMITER` | `:203` |
| `ARMOR_MINERAL` | `:207` |
| `ARMOR_PWR` | `:211` |
| `ARMOR_CRIT_VOL_FRAC` | `:215` |
| `SPECIFIC_SURFACE_AREA_EPSILON` | `:218` |
| `VOLUME_FRACTION_EPSILON` | `:221` |
| `PREFACTOR` (nested block) | `:224` |
| `SURFACE_AREA_FUNCTION` | `:331` |
| `SPECIFIC_SURFACE_AREA` | `:353` (units `'m^2/kg'`, `:356-357`) |
| `NUCLEATION_KINETICS` | `:358` |
| `case default` → `InputKeywordUnrecognized` | `:362-363` |

`SURFACE_AREA_FUNCTION` takes one of `CONSTANT` (`:337`), `POROSITY_RATIO` (`:339`), `VOLUME_FRACTION_RATIO` (`:341`), `POROSITY_VOLUME_FRACTION_RATIO` (`:343`), `MINERAL_MASS` (`:345`).

`PREFACTOR` opens a further nested block (push `:229`, pop `:316`) with cards `RATE_CONSTANT`/`PRECIPITATION_RATE_CONSTANT`/`DISSOLUTION_RATE_CONSTANT` (`:239-240`), `ACTIVATION_ENERGY` (`:256`), and `PREFACTOR_SPECIES` (`:264`) — the last of which is itself a keyword-prefixed named block: the species name is read as an argument on the card line (`:266-267`), then a block is pushed (`:269`) with cards `ALPHA` (`:279`), `BETA` (`:283`), `ATTENUATION_COEF` (`:287`).

So `MINERAL_KINETICS` produces **four levels of nesting** in a normal deck: `CHEMISTRY` → `MINERAL_KINETICS` → `<mineral>` → `PREFACTOR` → `PREFACTOR_SPECIES` → `<species>`.

### 4.2 Other dynamic-key blocks

| Block | Key read at | Sub-block pushed at | Notes |
|---|---|---|---|
| `CHEMISTRY,MINERAL_KINETICS` | `src/pflotran/reaction_mineral.F90:135` | `:149` | §4.1 |
| `CHEMISTRY,SORPTION,ISOTHERM_REACTIONS` | `src/pflotran/reaction_isotherm.F90:68` (comment `! first string is species name` at `:67`) | `:81` | cards incl. `TYPE` (`:94`), `DISTRIBUTION_COEFFICIENT` (`:114`), `LANGMUIR_B` (`:131`), `FREUNDLICH_N` (`:135`), `KD_MINERAL_NAME` (`:139`) |
| `CHEMISTRY,MINERAL_NUCLEATION_KINETICS` | `src/pflotran/reaction_mineral.F90:742` | `:745` (`InputPushBlock(input,nucleation%name,option)`) | hybrid: a `<TYPE> <name>` pair opens the block — type token at `:730` (`CLASSICAL` `:734` / `SIMPLIFIED` `:736`), then the name |
| `CHEMISTRY,SURFACE_COMPLEXATION_RXN,COMPLEX_KINETICS` | `src/pflotran/reaction_surf_complex.F90:114` | `:118` | cards `FORWARD_RATE_CONSTANT` (`:127`), `BACKWARD_RATE_CONSTANT` (`:131`). **Currently aborts** with an unsupported-feature message at `:102-105` |
| `UFD_DECAY` → `ELEMENT <name>` | `src/pflotran/pm_ufd_decay.F90:340` | `:343` | keyword-prefixed, not pure dynamic key; cards `SOLUBILITY` (`:352`), `KD` (`:355`, itself opening a block of positional `<material_name> <Kd>` rows at `:360`) |
| `UFD_DECAY` → `ISOTOPE <name>` | `src/pflotran/pm_ufd_decay.F90:452` | `:455` | cards `ELEMENT` (`:464`), `DECAY_RATE` (`:467`) |

**Dynamic-key *list* blocks** (key is data, but no sub-block — one row per name): `CHEMISTRY,MINERALS` (`src/pflotran/reaction_mineral.F90:65`), `ION_EXCHANGE_RXN,CATIONS` (`src/pflotran/reaction.F90:662-697`, row = `<cation> <K> [REFERENCE]`, the optional third token matched case-insensitively against `'REFERENCE'` at `:681`).

**Checked and *not* dynamic-key**, reported so the absence is on record:

- `reaction_microbial.F90` — `MONOD` (`:112-114`) and `BIOMASS` (`:165-170`) use an explicit `SPECIES_NAME` card (`:124-125`, `:180-181`).
- `reaction.F90:212` `SECONDARY_SPECIES` — a plain name list, no sub-block.
- `characteristic_curves.F90` and `material.F90` — these use the *named-top-level-block* form (`CHARACTERISTIC_CURVES <name>`, `MATERIAL_PROPERTY <name>`), which is a different production: the name follows a **fixed** keyword. No dynamic-key sub-block was found inside either.

> **Parser consequence.** A dynamic-key block is syntactically indistinguishable from a fixed-keyword block. The only way to know that the first token of a `MINERAL_KINETICS` row is data rather than a keyword is to know the enclosing block's identity. This is the strongest argument for the block-context stack described in `deck_grammar_and_reader.md` §5.

---

## 5. Positional data rows

> **Question.** In `CONSTRAINT`, `MINERALS` rows look like `Labradorite 0.144 5.2d2` and `CONCENTRATIONS` rows like `Ca++ 1.04d-7 T`. Document the exact column order and the trailing type codes.

**CONFIRMED** for both, with the exact column orders below. Note one refutation of a natural assumption: **there is no `GASES` sub-block inside `CONSTRAINT`** — gas constraints are a per-species row in `CONCENTRATIONS` with type code `G` (§5.2, §5.6).

### 5.1 Entering a `CONSTRAINT`

`CONSTRAINT <name>` is read at three sites, all of which read the name off the opening line with `InputReadWord(...,PETSC_TRUE)`:

| Context | `case('CONSTRAINT')` | Name read |
|---|---|---|
| Top-level `SUBSURFACE` | `src/pflotran/factory_subsurface_read.F90:1252` | `:1263` |
| Inline inside a `TRANSPORT_CONDITION` | `src/pflotran/condition.F90:4014` | `:4023` |
| Standalone reaction driver | `src/pflotran/pflotran_rxn.F90:128` | `:135` |

The body reader is chosen **by transport mode** (`src/pflotran/factory_subsurface_read.F90:1253-1262`):

- `RT_MODE` → `TranConstraintRTRead` (`src/pflotran/transport_constraint_rt.F90:202-767`)
- `NWT_MODE` → `TranConstraintNWTRead` (`src/pflotran/transport_constraint_nwt.F90:183-325`)

**These two readers accept different cards and a different type enum.** A parser must key on transport mode.

RT-mode card list (`select case` at `src/pflotran/transport_constraint_rt.F90:267`, default at `:750-751`):

| Card | Line |
|---|---|
| `CONC`, `CONCENTRATIONS` | `:267` |
| `FREE_ION_GUESS` | `:417` |
| `MNRL`, `MINERALS` | `:485` |
| `SURFACE_COMPLEXES` | `:591` |
| `IMMOBILE` | `:654` |

plus two inherited base cards tried first (`:264-265`, table at `src/pflotran/transport_constraint_base.F90:123-130`): `EQUILIBRATE_AT_EACH_CELL` (`:124`) and `DO_NOT_EQUILIBRATE_AT_EACH_CELL` (`:126`).

NWT-mode accepts **only** `CONC`/`CONCENTRATIONS` (`src/pflotran/transport_constraint_nwt.F90:227`) and does *not* call the base-card helper, so `EQUILIBRATE_AT_EACH_CELL` is not available there.

Two guards: an RT constraint without a preceding `CHEMISTRY` block is fatal (`src/pflotran/transport_constraint_rt.F90:243-247`), and a constraint with aqueous components but no concentrations sub-block is fatal (`:757-762`).

### 5.2 `CONCENTRATIONS` rows (RT mode) — `<name> <value> <type> [<aux>]`

Loop at `src/pflotran/transport_constraint_rt.F90:274-384` (push `:274`, exit test `:281`, pop `:384`). Row count is bounded by `reaction%naqcomp` (`:285-288`).

| Col | Content | Read at | Notes |
|---|---|---|---|
| 1 | primary species name | `:290` | `InputReadCard`; **no case folding**, species names are case-sensitive |
| 2 | concentration (double) | `:296-297` | |
| 3 | **constraint type code** | `:300` | upper-cased at `:305`; **mandatory** — a missing code is fatal at `:373-381` |
| 4 | constraining mineral/gas name | `:355-356` | **only** when col 3 is `M`, `G`, or `SC`; then mandatory (`:349-358`) |
| 4 | literal `DATASET` | `:360` | otherwise optional; if present, **col 5** is the dataset name (`:365-366`) and `external_dataset` is set (`:369`) |

Two subtleties for a rewriting parser:

- Column 3 is read with `InputReadCard` followed by `InputDefaultMsg` (`:300-302`), so the *read* is forgiving; the mandatory-ness is enforced separately by the `length > 0` test at `:304` and the explicit error at `:373-381`.
- In the non-mineral branch, an unrecognized fourth token is **silently ignored** — the inner `select case` at `:363-370` has no `case default`.

Example rows:

```
CONCENTRATIONS
  Ca++    1.04d-7   T                     # total aqueous
  H+      7.5       P                     # pH
  HCO3-   1.d-3     G   CO2(g)            # equilibrium with a named gas
  Na+     1.d-3     Z                     # charge balance
  Cl-     1.d-3     T   DATASET  cl_init  # value comes from a dataset
END
```

Post-loop validation: the number of rows must **exactly** equal `reaction%naqcomp` (`:386-397`), and duplicate names are rejected (`:399-412`).

Storage type: `aq_species_constraint_type` (`src/pflotran/reaction_aux.F90:101-111`).

### 5.3 `MINERALS` / `MNRL` rows — `<name> <vol_frac> <area> [<area_units>]`

Loop at `src/pflotran/transport_constraint_rt.F90:492-560`, bounded by `reaction%mineral%nkinmnrl` (`:502-507`).

| Col | Content | Read at |
|---|---|---|
| 1 | mineral name | `:509` |
| 2 | volume fraction (double) | `:528-529`, **or** the literal `DATASET` + a dataset name (`:519-526`) |
| 3 | specific surface area (double) | `:546-547`, **or** `DATASET` + name (`:536-543`) |
| 4 | **optional units token** | `:551-552`; defaults to `'m^2/m^3'` when absent (`:553-558`) |

The `DATASET` lookahead in columns 2 and 3 is implemented by the save-peek-restore idiom (`:516-517` and `:533-534`, restoring at `:521` / `:538`) described in `deck_grammar_and_reader.md` §4.2.

The source comment at `:550` says it plainly: *"read units if they exist. conversion takes place later"*. Conversion happens in `ReactionMnrlProcessConstraint` (`src/pflotran/reaction_mineral.F90:894`), which lowercases the token (`:996`) and accepts exactly three suffix families (`:997-1011`):

| Units suffix | Meaning | Internal |
|---|---|---|
| `…m^3_mnrl` | area per mineral volume | `'m^2/m^3'` |
| `…g` | area per mineral **mass** | `'m^2/kg'` |
| `…m^3` | area per **bulk** volume | (bulk-volume basis) |

Anything else is fatal (`:1008-1010`). So `32000 cm^2/g` is area-per-mineral-mass, while a bare `5.2d2` is area-per-mineral-volume in `m^2/m^3`.

Post-loop: **every** kinetic mineral must be listed (`:562-570`), duplicates rejected (`:572-584`).

Storage type: `mineral_constraint_type` (`src/pflotran/reaction_mineral_aux.F90:88-101`).

### 5.4 The other `CONSTRAINT` sub-blocks

| Sub-block | Loop | Columns |
|---|---|---|
| `FREE_ION_GUESS` | `src/pflotran/transport_constraint_rt.F90:424-451` | **2**: name (`:441-442`), value (`:448`). No type code, no units, no `DATASET`. Count must equal `reaction%naqcomp` (`:453-464`) |
| `SURFACE_COMPLEXES` | `:598-624` | **2**: name (`:615`), concentration (`:620-621`). No units. Under-count fatal (`:626-633`) |
| `IMMOBILE` | `:661-719` | **2 or 3**: name (`:678-679`), concentration (`:700-701`, or `DATASET` at `:689-694`), **optional units** (`:707`) with internal `'mol/m^3'` (`:705`) converted **immediately** (`:713-716`) — unlike `MINERALS`, where conversion is deferred |

### 5.5 `COORDINATES` and `LIST` rows (REGION)

`COORDINATES` is handled by `GeometryReadCoordinates` (`src/pflotran/geometry.F90:122-168`), rows by `GeometryReadCoordinate` (`:172-197`):

- exactly **3** unlabelled doubles per row: `x` (`:190`), `y` (`:192`), `z` (`:194`);
- terminator test at `:148`, but **no `InputPushBlock`/`InputPopBlock`** — unlike `POLYGON`, this sub-block is not pushed onto the breadcrumb stack;
- hard cap of 100 coordinates (`:141`), overflow fatal (`:150-158`).

`LIST` is handled by `RegionReadCellList` (`src/pflotran/region.F90:1100-1211`). The number of columns is discovered by a **lookahead on the first row** (`src/pflotran/region.F90:554-557`): read a line, save it, count words with `InputCountWordsInBuffer`, restore it. Then:

- 1 column → cell ids only, `DEFINED_BY_CELL_IDS` (`:559-561`, `:1132`);
- 2 columns → cell id + face id, `DEFINED_BY_CELL_AND_FACE_IDS` (`:562-564`, `:1130`);
- anything else → fatal, *"REGION LIST format only supported for CELL_ID or CELL_ID FACE_ID format. One or two integers per line."* (`:566-568`).

Column 1 is read at `:1156`, column 2 (only when faces are expected) at `:1170`.

### 5.6 The constraint-type enum

**RT mode** — `select case(word)` at `src/pflotran/transport_constraint_rt.F90:306`, after `StringToUpper` at `:305` (so codes are **case-insensitive**):

| Deck codes (verbatim) | Constant | Value | Case line | Meaning |
|---|---|---|---|---|
| `F`, `FREE` | `CONSTRAINT_FREE` | 1 | `:307` | free-ion concentration; converted molar→molal (`src/pflotran/reaction.F90:1547`) |
| `T`, `TOTAL` | `CONSTRAINT_TOTAL` | 2 | `:309` | total aqueous (label `'total aq'`, `src/pflotran/reaction.F90:2378`) |
| `L`, `LOG` | `CONSTRAINT_LOG` | 3 | `:331` | **base-10 log** of free concentration (`free_conc = (10.d0**conc)*…`, `src/pflotran/reaction.F90:1549`) |
| `P`, `PH` | `CONSTRAINT_PH` | 4 | `:327` | pH |
| `E`, `PE` | `CONSTRAINT_PE` | 5 | `:329` | pe |
| — *(no deck code)* | `CONSTRAINT_EH` | 6 | — | declared at `:28` but **never produced by any `case`** |
| `M`, `MINERAL`, `MNRL` | `CONSTRAINT_MINERAL` | 7 | `:333` | equilibrium with the mineral named in col 4 |
| `G`, `GAS` | `CONSTRAINT_GAS` | 8 | `:336` | equilibrium with the gas named in col 4 |
| `Z`, `CHARGE_BALANCE` | `CONSTRAINT_CHARGE_BAL` | 9 | `:341` | charge balance; value used only as an initial guess (`src/pflotran/reaction.F90:1550-1553`) |
| `TOTAL_SORB` | `CONSTRAINT_TOTAL_SORB` | 10 | `:311` | total sorbed, `mol/m^3` bulk (`src/pflotran/reaction.F90:1541`) |
| `SC`, `CONSTRAINT_SUPERCRIT_CO2` | `CONSTRAINT_SUPERCRIT_CO2` | 11 | `:338` | equilibrium with supercritical CO2 named in col 4 |
| `TOTAL_AQ_PLUS_SORB` | `CONSTRAINT_TOTAL_AQ_PLUS_SORB` | 12 | `:314` | aqueous + sorbed, `mol/m^3` bulk (`src/pflotran/reaction.F90:1544`); fatal unless equilibrium sorption is active (`:315-321`) |
| `S` | — | — | `:323` | **removed**; fatal: *"S" constraint type no longer supported as of March 4, 2013.* (`:324-325`) |

Constant declarations are `src/pflotran/transport_constraint_rt.F90:22-34`, under the comment `! concentration subcondition types` at `:21`. `CONSTRAINT_NULL = 0` (`:22`) is only the array initializer (`src/pflotran/reaction_aux.F90:792`).

The declarations carry no per-constant comments. The human-readable meanings above come from the output-label mapping at `src/pflotran/reaction.F90:2377-2397` and the numeric-semantics branch at `src/pflotran/reaction.F90:1540-1554`.

**Long-form aliases exist for every single-letter code** (see the table). Two codes are long-form only, with no letter: `TOTAL_SORB` and `TOTAL_AQ_PLUS_SORB`.

**NWT mode uses a completely different enum**, `select case(word)` at `src/pflotran/transport_constraint_nwt.F90:265`:

| Deck codes | Constant | Value | Case line | Meaning (from the declaration comments) |
|---|---|---|---|---|
| `AQ`, `AQUEOUS` | `CONSTRAINT_AQ_EQUILIBRIUM` | 1 | `:266` | constraint on aqueous concentration (`:14-15`) |
| `PPT`, `PRECIPITATED` | `CONSTRAINT_PPT_EQUILIBRIUM` | 2 | `:269` | constraint on mineral (precipitated) concentration (`:16-17`) |
| `SB`, `SORBED` | `CONSTRAINT_SB_EQUILIBRIUM` | 3 | `:272` | constraint on sorbed concentration (`:18-19`) |
| `T`, `TOTAL` | `CONSTRAINT_T_EQUILIBRIUM` | 4 | `:275` | constraint on total bulk concentration (`:20-21`) |
| `VF`, `PRECIPITATED_VOLUME_FRACTION` | `CONSTRAINT_MNRL_VOL_FRAC_EQ` | 5 | `:278` | constraint on mineral volume fraction (`:22-23`) |

`case default` is fatal with *"… Options include: VF, T, AQ, PPT, or SB only."* (`:281-288`).

> **Hazard.** `T` is valid in both modes but means `CONSTRAINT_TOTAL = 2` in RT and `CONSTRAINT_T_EQUILIBRIUM = 4` in NWT. Never interpret a constraint type code without knowing the transport mode.

---

## 6. Name resolution and its error messages

Resolution happens after reading, mostly in `PatchProcessCouplers` (`src/pflotran/patch.F90:257-847`).

### 6.1 The matchers

All name matchers use the same rule: `len_trim` equality **and** character-exact `StringCompare`. Matching is therefore **case-sensitive**, and the **first** match wins — there is no duplicate-name detection anywhere.

| Resolver | Location | Returns on miss |
|---|---|---|
| `RegionGetPtrFromList` | `src/pflotran/region.F90:1215-1248` (match at `:1240-1241`) | `null()` (`:1234`), no message |
| `MaterialPropGetPtrFromArray` | `src/pflotran/material.F90:1545-1580` (match at `:1568-1573`) | `null()` (`:1565`), no message |
| `FlowConditionGetPtrFromList` | `src/pflotran/condition.F90:4614-4648` (match at `:4638-4641`) | `null()` (`:4633`), no message |

Every caller must check the pointer itself and emit its own message.

### 6.2 Message shapes

| Reference | Resolve at | Message |
|---|---|---|
| region in a boundary condition | `src/pflotran/patch.F90:296-297` | `Region "<r>" in boundary condition "<c>" not found in region list` |
| region in an initial condition | `:383-384` | `Region "<r>" in initial condition "<c>" not found in region list` (`:386-389`) |
| region in a source/sink | `:440-441` | same shape |
| region in a prescribed condition | `:586-587` | same shape |
| **region in a strata** | `:670-671` | `Region "<r>" in strata not found in region list` (`:672-675`) — note the absence of a coupler name, because `STRATA` has none (§3.1) |
| **material in a strata** | `:684-687` | `Material "<m>" not found in material list` (`:688-692`) |
| region in an observation | `:721-722` | `Region "<r>" in observation point "<o>" not found in region list` (`:724-728`) |

The material link is gated: it is only attempted when a region **or** a dataset name was supplied and the strata is active (`src/pflotran/patch.F90:679-682`).

A separate bounds check runs after resolution, `RegionCheckCellIndexBounds` (`src/pflotran/region.F90:1252-1297`), whose message names the offending region and the grid's legal id range (`:1287-1293`).

> **Parser consequence.** These messages are the *only* signal that a name is wrong, and they are emitted long after the deck line that contained the typo. A parser that rewrites or generates names should validate the declare/reference graph itself rather than relying on PFLOTRAN's diagnostics.

---

## 7. `FLOW_CONDITION` — where the values actually live

Flow conditions are the blocks a calibration agent most often needs to rewrite, so their value grammar is worth stating explicitly.

### 7.1 Mode-specific readers

There are **six** condition readers in `condition.F90`, each with its own `TYPE` sub-block:

| Reader | Line range | `case('TYPE')` |
|---|---|---|
| `FlowConditionRead` | `src/pflotran/condition.F90:1061-2020` | `:1213` |
| `FlowConditionGeneralRead` | `:2024-2634` | `:2121` |
| `FlowConditionSCO2Read` | `:2638-3166` | `:2730` |
| `FlowConditionHydrateRead` | `:3170-3774` | `:3265` |
| `TranConditionRead` | `:3860-4106` | `:3928` |
| `GeopConditionRead` | `:4110-4176` | `:4151` |

Which one runs depends on `option%iflowmode`, set from the `SIMULATION` block's `PROCESS_MODELS` → `MODE` card (`src/pflotran/factory_subsurface_read.F90:76-115`).

### 7.2 The `UNITS` card — a per-block default

`FlowConditionRead` supports a `UNITS` card (`src/pflotran/condition.F90:1162`) that sets **default units for the whole condition**, consumed in a loop until the line is exhausted (`:1163-1191`). The accepted tokens are a closed list, matched **case-sensitively** and routed by which sub-condition they belong to:

| Tokens | Applies to | Line |
|---|---|---|
| `s`, `sec`, `min`, `hr`, `d`, `day`, `y`, `yr` | `condition%time_units` | `:1167-1168` |
| `mm`, `cm`, `m`, `met`, `meter`, `dm`, `km` | `condition%length_units` | `:1169-1170` |
| `Pa`, `KPa` | pressure | `:1171-1172` |
| `kg/s`, `kg/yr` | rate | `:1173-1174` |
| `W`, `J/yr` | energy rate | `:1175-1176` |
| `W/m^2`, `J/m^2/yr` | energy flux | `:1177-1178` |
| `m/s`, `m/yr` | flux | `:1179-1180` |
| `C`, `K` | temperature | `:1181-1182` |
| `M`, `mol/L` | concentration | `:1183-1184` |
| `kJ/mol` | enthalpy | `:1185-1186` |

Anything else is fatal (`:1187-1189`). Note this list is **narrower** than what `units.F90` can convert, and note the spellings that differ from `units.F90`'s own tables: `KPa` here versus `kPa` in `src/pflotran/units.F90:520`, and `hr` here where `units.F90` also accepts `h`/`hour`. See `units_and_conversion.md` §6.

Defaults established before the loop: temperature `'C'`, concentration `'M'`, enthalpy `'kJ/mol'` (`src/pflotran/condition.F90:1141-1143`).

### 7.3 The value slot: keyword-or-number lookahead

`ConditionReadValues` (`src/pflotran/condition.F90:4180-4316`) implements the production `<CARD> ( FILE <f> | DATASET <name> | LIST … | DBASE_VALUE <key> | <number> )`. The disambiguation is a **save / read / classify / restore** lookahead:

```fortran
string2 = trim(input%buf)                                  ! :4238  save
call InputReadWord(input,option,word,PETSC_TRUE)           ! :4239  read one token
call StringToUpper(word)                                   ! :4241
length = len_trim(word)
if (StringStartsWithAlpha(word)) then                      ! :4243  classify
  ...  FILE (:4245) / DATASET (:4280) / LIST (:4288) / DBASE_VALUE (:4292)
  else
    ... 'Keyword "<w>" not recognized in when reading condition values ...'  ! :4298-4301
else
  input%buf = trim(string2)                                ! :4304  restore
  call DatasetAsciiReadSingle(...)                         ! :4306-4307  parse as a number
endif
```

`StringStartsWithAlpha` (`src/pflotran/string.F90:398-421`) is the discriminator: **a token beginning with a letter is a keyword; anything else is a number.** This is why a value may be written `1.d-7`, `.5`, or `-999` but not, say, `e7`.

Note the asymmetry at `:4292`: `DBASE_VALUE` is detected here *and* independently inside `InputReadDouble` (`src/pflotran/input_aux.F90:610-612`), because the buffer is restored to `string2` at `:4293` before delegating.

---

## 8. Things not established from static reading

- **Whether the `.h5` region path and the ASCII path accept the same `def_type` set** was not traced beyond `src/pflotran/init_common.F90:237-253`; the HDF5 readers are external-library-heavy (HDF5's `h5*` API) and were not followed.
- **The exact semantics of a two-row `COORDINATES` block** (min corner / max corner) is a convention imposed by the grid localization code, not by `geometry.F90`; it was not traced to its consumer.
- **Whether any deck can legally omit column 3 of a `CONCENTRATIONS` row.** The read is forgiving (`src/pflotran/transport_constraint_rt.F90:300-302`) but the immediately following `length > 0` test makes omission fatal at `:373-381`. No path was found that reaches the `else` branch benignly, but the two-step structure suggests one was once intended.
- **Geomechanics parallels.** `GeomechRegionRead` (`src/pflotran/geomechanics_region.F90:197`) and `GeomechStrataRead` (`src/pflotran/geomechanics_strata.F90:145`) are separate readers with their own card sets, dispatched from `src/pflotran/init_subsurface_geomechanics.F90:179` and `:335`. They were not analyzed here. A deprecated surface-flow variant exists under `src/pflotran/.deprecated/` and should not be modelled.
- **`CONSTRAINT_EH`** is declared (`src/pflotran/transport_constraint_rt.F90:28`) but no deck code produces it. Whether it is reachable through some other path (restart, HDF5 initial condition) was not determined.
