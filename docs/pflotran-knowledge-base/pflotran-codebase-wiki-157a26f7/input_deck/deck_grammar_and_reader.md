**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** input deck grammar and the core reader (`input_aux.F90`, `string.F90`)
**Last verified:** 2026-07-31

---

# PFLOTRAN Input Deck: Grammar and Reader

## 0. What this document is, and what it is not

This document describes **how PFLOTRAN tokenizes, blocks, and reads its ASCII input deck** — the machinery in `src/pflotran/input_aux.F90` and `src/pflotran/string.F90`, plus the way the rest of the code calls into it. It is written for two readers: an AI calibration agent that must reason about deck semantics, and a parser author who must mechanically **locate and rewrite a numeric value** in a deck without corrupting it.

It is **not** a card catalogue. PFLOTRAN has no such thing in one place (see §5), and each physics subsystem's cards are documented in sibling topics.

Two companion files complete this topic:

- `conditions_regions_strata.md` — the `CONSTRAINT` / `REGION` / `STRATA` blocks, positional data rows, and name-based cross-referencing.
- `units_and_conversion.md` — the optional trailing unit token and `units.F90`.

**Citation convention.** Every substantive claim below carries a `(src/pflotran/<file>.F90:NNN)` citation, verified by reading the source at commit `157a26f7`. PETSc and HDF5 symbols are external framework and are labelled as such where they appear.

---

## 1. Executive summary for a parser author

If you read nothing else, read this.

1. **There is no grammar, no BNF, and no central dispatch table.** The deck is read by ~120 hand-written block-reader subroutines, each with its own `select case` over keyword string literals. Keyword meaning is determined *entirely* by which subroutine is currently executing. See §5 — this is the single most important fact in this document.
2. **The reader is line-oriented and stateful.** One line is pulled into a single buffer `input%buf`, then destructively consumed left-to-right, token by token (§3, §4).
3. **Blocks close on `/` OR `END` OR any token starting with `END_`** — but only where the enclosing reader calls `InputCheckExit()`. At least one important block (`SUBSURFACE`) does *not* call it (§6).
4. **Both `#` and `!` start comments, anywhere in a line** — including in the middle of a filename (§7).
5. **A numeric slot may not contain a number.** `DBASE_VALUE <key>` substitutes a value from an external database file at read time (§11). A rewriting parser must handle this or it will silently corrupt decks.
6. **A numeric value may be followed by an optional unit token** whose absence is legal and silently means "already in internal units" (§10, and `units_and_conversion.md`).
7. **Line-leading token length is hard-capped at 40 characters** and keywords at 32 (§4.3).

---

## 2. The reader object and the file stack

### 2.1 `input_type`

The entire reader state is one derived type (`src/pflotran/input_aux.F90:14-26`):

```fortran
type, public :: input_type
  PetscInt :: fid                                   ! :15  Fortran unit number
  PetscInt :: line_number                           ! :16  for error messages
  PetscErrorCode :: ierr                            ! :17  sticky error flag
  character(len=MAXSTRINGLENGTH) :: path, filename  ! :18-19
  character(len=MAXSTRINGLENGTH) :: buf             ! :20  THE current line buffer
  character(len=MAXSTRINGLENGTH) :: err_buf,err_buf2! :21-22 error context
  PetscBool :: broadcast_read                       ! :23  MPI read mode
  PetscBool :: force_units                          ! :24  make units mandatory
  type(input_type), pointer :: parent               ! :25  external-file stack link
end type input_type
```

`MAXSTRINGLENGTH = 512` and `MAXWORDLENGTH = 32` (`src/pflotran/pflotran_constants.F90:33-34`). **`input%buf` is the whole parser state for the current line** — there is no token list, no lookahead structure, no AST.

`input%ierr` is a *sticky* flag: most read routines short-circuit when it is set (`src/pflotran/input_aux.F90:1121`, `:1204`, `:901`), so an error propagates until something explicitly clears it.

Three error codes exist (`src/pflotran/pflotran_constants.F90:316-318`):

| Constant | Value | Meaning |
|---|---|---|
| `INPUT_ERROR_NONE` | 0 | no error |
| `INPUT_ERROR_DEFAULT` | 1 | generic read failure (EOF, blank where a token was required, unparseable number, NaN) |
| `INPUT_ERROR_KEYWORD_LENGTH` | 2 | token longer than the destination character variable |

`InputError()` is simply `ierr /= INPUT_ERROR_NONE` (`src/pflotran/input_aux.F90:1572-1576`).

### 2.2 File opening and the `EXTERNAL_FILE` stack

`InputCreate1()` (`src/pflotran/input_aux.F90:162-230`) splits the supplied filename into a directory `path` and a bare `filename` by a backwards search for `/` (`:202-209`), then opens the unit (`:218`). A missing file is fatal (`:220-226`).

Decks may be **nested**. `EXTERNAL_FILE <filename>` pushes a new `input_type` whose `parent` points at the current one (`InputPushExternalFile`, `src/pflotran/input_aux.F90:2649-2672`); reaching EOF on the child pops back to the parent and continues (`InputPopExternalFile`, `:2676-2700`, called from the read loop at `:790`). Nesting depth is capped by `MAX_IN_UNIT = 27` (`src/pflotran/pflotran_constants.F90:51`), enforced at `src/pflotran/input_aux.F90:211-215`.

Relative filenames inside an included file are resolved against the **parent deck's** path, not the included file's: `InputReadFilename()` prepends `input%path` unless the name is absolute (`src/pflotran/input_aux.F90:1313-1315`).

> **Parser consequence.** A "deck" is a *tree of files*, not one file. `EXTERNAL_FILE` is recognized by a raw `long_word(1:13) == 'EXTERNAL_FILE'` prefix test inside the line-fetch loop (`src/pflotran/input_aux.F90:804`), i.e. it is handled *below* the block level and can appear anywhere, including in the middle of a block.

### 2.3 Parallel reading

When `input%broadcast_read` is set, only the I/O rank actually reads; the buffer is then MPI-broadcast to all ranks (`src/pflotran/input_aux.F90:737-751`, using MPI's `MPI_Bcast` — external framework). Otherwise every rank reads the file independently (`:750`). This does not affect grammar.

---

## 3. The line pipeline: `InputReadPflotranString`

`InputReadPflotranStringSlave()` (`src/pflotran/input_aux.F90:757-882`) is the routine that fills `input%buf` with the next *significant* line. Understanding its loop is understanding the deck's lexical layer.

Per iteration (`src/pflotran/input_aux.F90:783-851`):

1. `input%line_number` is incremented and one record is read with `read(input%fid,'(a)',...)` (`:784-785`).
2. `StringAdjustl(input%buf)` left-justifies, **converting leading tabs to spaces first** because Fortran's intrinsic `adjustl` does not strip tabs (`src/pflotran/string.F90:503-534`, rationale at `:505-507`).
3. On a read error (EOF), the external-file stack is popped and the loop retried; if there is no parent, the loop exits with `ierr` set (`src/pflotran/input_aux.F90:788-795`).
4. **Whole-line comment test:** `if (input%buf(1:1) == '#' .or. input%buf(1:1) == '!') cycle` (`:797`). Because step 2 already left-justified, leading whitespace and tabs before the comment character are permitted.
5. The first token (up to 40 chars) is extracted into `long_word` from a *copy* of the buffer and upper-cased (`:799-802`).
6. `EXTERNAL_FILE` prefix → push a nested file and `cycle` (`:804-810`).
7. `SKIP` → swallow lines until a matching `NOSKIP`, honouring nesting via `skip_count` (`:811-847`). The guard `if (len_trim(long_word) > 4) exit` at `:814-816` exists "to avoid keywords that start with SKIP" (comment at `:813`), and the equivalent `len_trim(long_word) == 4` test at `:836` means only a bare `SKIP` increments the nesting counter. Hitting EOF inside a `SKIP` is fatal with the message *"End of file reached in InputReadPflotranStringSlave. SKIP encountered without a matching NOSKIP."* (`:824-827`).
8. Otherwise, if the first character of the first token is non-blank and the token is not `NOSKIP`, **exit the loop** — the line is significant (`:848-850`).

**Blank lines are skipped** as a side effect of step 8: a blank line yields a blank `long_word`, so `long_word(1:1) /= ' '` is false and the loop cycles.

### 3.1 The inline-comment strip

After a significant line is found, a copy-until-comment-character loop (`src/pflotran/input_aux.F90:854-864`) rebuilds the buffer, copying characters while `tempstring(i:i) /= '#' .and. tempstring(i:i) /= '!'` (`:858`) and exiting at the first hit (`:861`). The buffer is truncated at the **first** `#` or `!` anywhere in the line. This is a raw character scan with **no quoting or escaping awareness whatsoever**.

### 3.2 Long-keyword guard

`CatchLongKeywordError()` (`src/pflotran/input_aux.F90:868-880`) is an internal procedure that fires when the first-token extraction failed on a *non-blank* line. Its message names the 40-character limit explicitly (`:876`): *"Perhaps the keyword is greater than 40 characters."* The limit comes from `PetscInt, parameter :: num_chars = 40` (`:774`).

Note the deliberate early-return at `:871`: `if (len_trim(input%buf) == 0) return`. That is what makes blank lines harmless rather than fatal, even though extracting a token from them sets `ierr`.

---

## 4. The tokenizer: `InputReadNChars2`

Every word, integer, and real is ultimately produced by one routine (`src/pflotran/input_aux.F90:1212-1289`). Its behaviour *is* the deck's token grammar.

### 4.1 Delimiters

```fortran
character(len=1), parameter :: tab = achar(9), backslash = achar(92)   ! :1232
...
! Remove leading blanks and tabs
do while((string(i:i) == ' ' .or. string(i:i) == ',' .or. &
         string(i:i) == tab) .and. i <= length)                        ! :1252-1253
...
! Count # of continuous characters (no blanks, commas, etc. in between)
do while (string(i:i) /= ' ' .and. string(i:i) /= ',' .and. &
          string(i:i) /= tab  .and. &
          (i == begins .or. string(i:i) /= backslash))                 ! :1269-1271
```

**Token separators are: space, comma, and tab** (`src/pflotran/input_aux.F90:1252-1253`, `:1269-1270`). Commas are interchangeable with spaces — `1.0, 2.0, 3.0` and `1.0 2.0 3.0` tokenize identically. Runs of separators collapse.

**Backslash terminates a token** unless it is the token's first character (`:1271`). This is how Windows-style path fragments survive as a single leading token but otherwise split.

There is **no quoting** in this routine. Quoted strings are only supported by the separate `InputReadQuotedWord()` → `StringReadQuotedWord()` path (`src/pflotran/input_aux.F90:1321-1340`, `src/pflotran/string.F90:313-394`), which is opt-in per call site and honours single quotes `'` only (`src/pflotran/string.F90:358`, `:366`). Double quotes are not special anywhere in the reader.

### 4.2 Destructive consumption

The routine ends with `chars = string(begins:ends)` (`:1283`) followed by `string = string(ends+1:)` (`:1285`) — reading a token **removes it from the buffer**. This is why the reader has no need for a cursor, and why "read the keyword, then read its arguments" works: each call eats from the front of `input%buf`.

Two consequences worth internalizing:

- A block reader that reads fewer arguments than a line supplies **silently ignores the remainder**. The leftovers are discarded when the next line is fetched.
- Several call sites exploit this by *saving and restoring* the buffer to implement one-token lookahead — see `src/pflotran/condition.F90:4238` (`string2 = trim(input%buf)`) and `:4304` (`input%buf = trim(string2)`), and `src/pflotran/input_aux.F90:2176`/`:2186` in the DBASE path.

### 4.3 Length limits

`InputReadNChars2` sets `INPUT_ERROR_KEYWORD_LENGTH` if the token is longer than the destination (`src/pflotran/input_aux.F90:1277-1280`). Practical caps:

| Read via | Destination length | Cap |
|---|---|---|
| `InputReadWord` | `MAXWORDLENGTH` | **32 chars** (`src/pflotran/input_aux.F90:1145`, `src/pflotran/pflotran_constants.F90:34`) |
| first token of any line, during line fetch | `num_chars` | **40 chars** (`src/pflotran/input_aux.F90:774`) |
| `InputReadFilename` | `MAXSTRINGLENGTH` | **512 chars** (`src/pflotran/input_aux.F90:1308-1309`) |
| whole line | `MAXSTRINGLENGTH` | **512 chars** (`src/pflotran/input_aux.F90:20`) |

The 32-character cap applies to **keywords and to names** (region names, material names, condition names) since those are read with `InputReadWord` — e.g. `src/pflotran/factory_subsurface_read.F90:1189` reads `region%name` that way. The error message for the length case is specialized at `src/pflotran/input_aux.F90:373-376`.

### 4.4 Blank-line policy: `return_blank_error`

Every tokenizing call passes a `return_blank_error` logical. When the buffer is exhausted:

- `PETSC_TRUE` → `ierr = INPUT_ERROR_DEFAULT` (`src/pflotran/input_aux.F90:1241-1242`), i.e. "this token was mandatory".
- `PETSC_FALSE` → `ierr = INPUT_ERROR_NONE` (`:1243-1244`), i.e. "this token was optional".

**This flag is the mechanism by which optional trailing tokens (notably units) are expressed.** There is no other optionality marker in the reader.

---

## 5. Keyword dispatch — the central question

> **Question.** The same keyword means different things depending on its parent block. `CHARACTERISTIC_CURVES` is a named block at top level but a by-name *reference* inside `MATERIAL_PROPERTY`. `PERMEABILITY` opens a sub-block under `MATERIAL_PROPERTY` but names a variable in an `OUTPUT`/`VARIABLES` list. `TYPE` opens a sub-block in `FLOW_CONDITION` but takes a scalar in `GRID`. How does the reader disambiguate? Is there a central card dispatch table?

### 5.1 Verdict: there is no central table. Dispatch is positional-by-call-stack.

**CONFIRMED, and the mechanism is that each block reader parses its own block independently.** A keyword has no global identity at all. Its meaning is determined solely by *which subroutine's `select case` happens to be executing when that token is read.*

Mechanical evidence at this commit:

| Measure | Count | How measured |
|---|---|---|
| Files calling `InputReadPflotranString` | 122 | `grep -rl` over `src/pflotran/*.F90` |
| `InputCheckExit(` call sites outside `input_aux.F90` | 346 | `grep -rn` |
| `InputPushBlock` call sites outside `input_aux.F90` | 297 | `grep -rn` |
| `InputKeywordUnrecognized(` call sites outside `input_aux.F90` | 397 | `grep -rn` |
| Central card/keyword table | **0** | `grep -rn "card_table\|keyword_table\|dispatch"` returns nothing |

`input_aux.F90` exports **no** dispatch entry point. Its public list (`src/pflotran/input_aux.F90:126-156`) contains only line-fetch, tokenize, error, logging, and units helpers. There is nothing in it that maps a string to a handler.

### 5.2 The canonical block-reader idiom

Essentially every block in PFLOTRAN is read by this shape (example: `MaterialPropertyRead`, `src/pflotran/material.F90:294-1164`):

```fortran
call InputPushBlock(input,option)                        ! material.F90:337
do
  error_str = 'MATERIAL_PROPERTY'                        ! :339
  call InputReadPflotranString(input,option)             ! :340
  if (InputCheckExit(input,option)) exit                 ! :342
  call InputReadCard(input,option,keyword)               ! :344
  call InputErrorMsg(input,option,'keyword',error_str)   ! :345
  call StringToUpper(keyword)                            ! :346
  select case(trim(keyword))                             ! :348
    case('NAME') ... case('ID') ...                      ! :350, :353
    case default                                         ! (per-block)
      call InputKeywordUnrecognized(input,keyword,error_str,option)
  end select
enddo
call InputPopBlock(input,option)
```

Recursion into a sub-block is nothing more than **a nested copy of the same loop inside one `case`**. That is literally all "nesting" means here.

### 5.3 Worked disambiguation examples, verified

**(a) `CHARACTERISTIC_CURVES` — block at top level, name reference inside `MATERIAL_PROPERTY`.**

At top level, in the `SUBSURFACE` dispatcher, it creates an object, reads a **name** off the same line, and recurses into a dedicated reader (`src/pflotran/factory_subsurface_read.F90:1628`, name read at `:1650-1652`, recursion at `:1656`):

```fortran
case ('CHARACTERISTIC_CURVES')
  characteristic_curves => CharacteristicCurvesCreate()                   ! :1649
  call InputReadWord(input,option,characteristic_curves%name,PETSC_TRUE)  ! :1650  <- name
  call CharacteristicCurvesRead(characteristic_curves,input,option)       ! :1656  <- recurse
```

Inside `MATERIAL_PROPERTY`, the *same string* is a leaf card that stores a name for later resolution, aliased to the legacy keyword `SATURATION_FUNCTION` (`src/pflotran/material.F90:366-369`):

```fortran
case('SATURATION_FUNCTION','CHARACTERISTIC_CURVES')
  call InputReadCardDbaseCompatible(input,option, &
                     material_property%saturation_function_name)
```

Note this reference is read through `InputReadCardDbaseCompatible` (`src/pflotran/input_aux.F90:1151-1181`), so **even a by-name reference can be a `DBASE_VALUE` substitution** (§11).

**(b) `PERMEABILITY` — sub-block opener under `MATERIAL_PROPERTY`, variable name under `OUTPUT`.**

Under `MATERIAL_PROPERTY` it opens a nested loop (`case` at `src/pflotran/material.F90:536`, `InputPushBlock` `:542`, fetch `:544`, `InputCheckExit` `:547`) whose card set is entirely disjoint from the parent's — `ANISOTROPIC` (`:553`), `ISOTROPIC` (`:563`), `PERM_X` (`:569`), `PERM_X_LOG10` (`:581`), `PERM_ISO` (`:624`), and a dozen more tensor-component variants through `:624`.

In the output-variable namespace the same string is a leaf selecting an output field, with units `'m^2'` and id `PERMEABILITY` (`src/pflotran/output_aux.F90:1061-1065`, inside `OutputVariableToID` beginning at `:753`).

**(c) `TYPE` — sub-block opener in `FLOW_CONDITION`, scalar-plus-modifier in `GRID`.**

In `FlowConditionRead` (`src/pflotran/condition.F90:1061-2020`), `TYPE` opens a nested loop assigning a boundary-condition type per degree of freedom (`case` at `:1213`, `InputPushBlock` `:1214`, fetch `:1216`, `InputCheckExit` `:1219`). Inside, the first token on each row selects the degree of freedom (`LIQUID_PRESSURE` `:1226` … `ENTHALPY` `:1244`) and the *second token on the same row* selects the BC kind (`DIRICHLET` `:1256`, `NEUMANN` `:1258`, `MASS_RATE` `:1260`, `HYDROSTATIC` `:1313`, `ZERO_GRADIENT` `:1317`, …). Some kinds take a *third* token as a subtype (`NEIGHBOR_PERM` `:1296`, `VOLUME` `:1298`, `PERM` `:1300`), mandatory when present (`:1307-1312`). The bare legacy spellings `PRESSURE`, `SATURATION`, `FLUX` are hard-deprecated with a fatal message (`:1246-1247`).

Note there are **six** independent `case('TYPE')` sites in `condition.F90` alone (`:1213`, `:2121`, `:2730`, `:3265`, `:3928`, `:4151`), one per flow-mode-specific condition reader (`FlowConditionRead` `:1061`, `FlowConditionGeneralRead` `:2024`, `FlowConditionSCO2Read` `:2638`, `FlowConditionHydrateRead` `:3170`, `TranConditionRead` `:3860`, `GeopConditionRead` `:4110`). **The same card in the same-named block means different things depending on the active flow mode.**

In `GRID`, `TYPE` is a scalar card that reads one word plus an optional refinement word (`src/pflotran/discretization.F90:171-176`):

```fortran
case('TYPE')
  call InputReadCard(input,option,discretization%ctype)
  call InputErrorMsg(input,option,'type','GRID')
  call StringToUpper(discretization%ctype)
  select case(trim(discretization%ctype))
    case('STRUCTURED')                       ! :176
```

with `STRUCTURED` optionally followed by `CARTESIAN` / `CYLINDRICAL` / `SPHERICAL` (`:181-186`), defaulting to `CARTESIAN` when absent (`:187-189`), and `UNSTRUCTURED`, `UNSTRUCTURED_EXPLICIT`, `UNSTRUCTURED_POLYHEDRA`, `ECLIPSE` as the alternative family (`:192-193`).

### 5.4 What a parser must therefore do

**A PFLOTRAN deck cannot be parsed with a flat keyword table. It must be parsed with a block-context stack.** To resolve a keyword you need the ordered list of enclosing block names, and — for anything under a flow or transport condition — the simulation's active mode, which is itself declared elsewhere in the deck (`SIMULATION` → `PROCESS_MODELS` → `MODE`, `src/pflotran/factory_subsurface_read.F90:72-115`).

The one thing PFLOTRAN gives you for free is that **it maintains this exact stack itself**, purely for error messages: `option%keyword_log` is a comma-joined breadcrumb of enclosing block names, pushed by `InputPushBlock` (`src/pflotran/input_aux.F90:1034-1070`) and popped by `InputPopBlock` (`:1074-1102`). The stack is a fixed array `keyword_block_map(20)` (`src/pflotran/option.F90:105`) — i.e. **a hard nesting-depth ceiling of 20**, written without a bounds check at `src/pflotran/input_aux.F90:1064-1068`. At end of reading, a non-zero residual count is a fatal internal-consistency error (`InputCheckKeywordBlockCount`, `:2750-2772`).

Mirroring `keyword_log` is the cheapest way for an external parser to stay aligned with PFLOTRAN's own notion of context.

### 5.5 The deck is read in multiple passes

Additionally, the deck is **not** read once top to bottom. Several passes rewind the file and seek a named top-level block by string match:

| Block sought | Seek site |
|---|---|
| `SIMULATION` | `src/pflotran/factory_pflotran.F90:137` and `src/pflotran/factory_forward.F90:136-138` (two separate passes) |
| `SUBSURFACE` | `src/pflotran/factory_subsurface_read.F90:740` (required-cards pre-pass) and `:1060-1063` (main read) |
| `WASTE_FORM_GENERAL` | `src/pflotran/factory_subsurface_linkage.F90:560` |
| `UFD_DECAY` | `src/pflotran/factory_subsurface_linkage.F90:637` |
| `UFD_BIOSPHERE` | `src/pflotran/factory_subsurface_linkage.F90:704` |
| `MATERIAL_TRANSFORM_GENERAL` | `src/pflotran/factory_subsurface_linkage.F90:903` |
| `WELL_MODEL_OUTPUT` | `src/pflotran/factory_subsurface_linkage.F90:1039` |
| `WIPP_SOURCE_SINK` | `src/pflotran/factory_subsurface_linkage.F90:1118` |
| `GEOTHERMAL_FRACTURE_MODEL` | `src/pflotran/factory_subsurface_linkage.F90:1165` |

`InputFindStringInFile3` (`src/pflotran/input_aux.F90:1397-1464`) reads forward looking for a line **whose first token exactly equals** the sought string (`:1433`, using `StringCompare` with an explicit length equality test). If not found it rewinds once and re-scans (`:1442-1456`) — an optimization for the common case of blocks appearing in file order — and warns if still absent (`:1458-1462`).

> **Parser consequence.** Block *order* in the file is largely irrelevant to PFLOTRAN, and a top-level block name must be the very first token on its line to be findable.

---

## 6. Block termination — `/` versus `END`

> **Question.** We observe blocks closed by either `/` or `END`, used inconsistently within one file. Are they exactly equivalent? Is a stray terminator tolerated?

### 6.1 Verdict on equivalence: CONFIRMED — `/` and `END` are exactly equivalent, plus a third form `END_*`

One function decides (`InputCheckExit`, `src/pflotran/input_aux.F90:1493-1534`):

```fortran
input%buf = adjustl(input%buf)                            ! :1514  (leading tabs skipped :1517)
if (input%buf(i:i) == '/' .or. &                          ! :1521
!geh: this fails when the keyword starts with END
!geh      StringCompare(input%buf(i:),'END',THREE_INTEGER)) then
    StringCompare(input%buf(i:),'END') .or. &             ! :1524
    ! to end a block, e.g. END_SUBSURFACE
    StringStartsWith(input%buf(i:),'END_')) then          ! :1526
  InputCheckExit = PETSC_TRUE
else
  InputCheckExit = PETSC_FALSE
endif
option%keyword_buf = ''                                   ! :1532  (side effect, always)
```

Three accepted terminator forms, with **identical effect** — the function returns a single boolean and every caller does the same thing with it (`exit` the block loop):

1. **`/`** — matched on the first non-blank, non-tab character only (`:1521`). Anything after the slash on the same line is ignored, because the whole line is discarded on the next fetch.
2. **`END`** — matched by `StringCompare2` (`src/pflotran/string.F90:154-184`), which first requires `len_trim` equality (`:167-172`). So the remainder of the line must be *exactly* `END`, nothing more.
3. **`END_<anything>`** — matched by `StringStartsWith` (`src/pflotran/string.F90:425-461`), the form used for `END_SUBSURFACE`, and by extension any `END_FOO`.

`END` is **case-sensitive here**: `InputCheckExit` does not upper-case the buffer, and both comparison helpers are exact-character (`src/pflotran/string.F90:175`, `:453`). Lowercase `end` will *not* terminate a block; it will be read as a keyword and hit the enclosing block's `case default` → fatal "not recognized".

**Documented discrepancy.** The routine's own docstring claims it checks for `.` as well — *"Checks whether an end character (.,/,'END') has been found"* (`src/pflotran/input_aux.F90:1495`). **The code does not check `.`.** A lone `.` is not a terminator. Trust the code.

### 6.2 Verdict on consistency: REFUTED for the top level — termination is *not* uniform

`InputCheckExit` is called by 346 sites, but **not by every block loop**. The most conspicuous exception is the top-level `SUBSURFACE` block itself (`src/pflotran/factory_subsurface_read.F90:1065-1078`):

```fortran
call InputPushBlock(input,'SUBSURFACE',option)       ! :1065
do
  call InputReadPflotranString(input,option)         ! :1067
  if (InputError(input)) exit                        ! :1068   <-- no InputCheckExit
  call InputReadCard(input,option,word,PETSC_FALSE)  ! :1070
  call StringToUpper(word)                           ! :1071
  card = trim(word)                                  ! :1072
  select case(trim(card))                            ! :1077
```

Instead, `END_SUBSURFACE` is an ordinary `case ... exit` in the dispatch table (`src/pflotran/factory_subsurface_read.F90:2572-2573`), and anything unmatched is fatal via `InputKeywordUnrecognized(input,word,'SubsurfaceReadInput()',option)` (`:2575-2577`).

**Therefore a bare `/` or `END` at top level inside `SUBSURFACE` is a fatal error, not a terminator** — the exact opposite of the behaviour one level down. Note also that `StringToUpper` at `:1071` means top-level card names *are* case-insensitive, while `InputCheckExit`'s `END` is not.

By contrast the `SIMULATION` block *does* use `InputCheckExit` (`src/pflotran/factory_forward.F90:143`), so `SIMULATION` accepts `/`, `END`, and `END_SIMULATION` interchangeably. This asymmetry between the two outermost blocks is real and is worth encoding as a special case in any parser.

### 6.3 Verdict on stray-terminator leniency: CONFIRMED, with a precise mechanism

There is no explicit "tolerate an extra terminator" code anywhere. The leniency that decks appear to enjoy is an **emergent property of two facts**:

1. `InputCheckExit` is evaluated at the *top* of each block loop, immediately after fetching a line, before any keyword is read (e.g. `src/pflotran/material.F90:340-342`).
2. Nested block loops are lexically nested, so control returns to the parent loop, which fetches the *next* line and immediately tests it too.

So an extra terminator line after a legitimately-closed nested block is not "tolerated" — it **silently closes the parent block as well**. This is a semantic hazard, not a courtesy: a deck with one surplus `/` will parse successfully but with the remaining cards of the parent block re-interpreted in the grandparent's namespace. Typically that produces a confusing "keyword not recognized" far from the real mistake, but it can also parse cleanly and change the model.

The one genuine safety net is the block-count balance check at end of read (`InputCheckKeywordBlockCount`, `src/pflotran/input_aux.F90:2750-2772`), which errors if pushes and pops did not balance — and which explicitly asks the user to email the developers (`:2767-2768`), confirming it is meant to catch reader bugs rather than deck typos.

### 6.4 A derived leniency worth flagging

`StringStartsWith(string,string2)` computes `length = min(len_trim(string),len_trim(string2))` (`src/pflotran/string.F90:444`) and compares only that many characters. When it is called as `StringStartsWith(input%buf(i:),'END_')` and the buffer holds a **shorter** string, the comparison length shrinks to the buffer's length.

Consequence, derived by reading rather than by running: **a line whose entire content is `E` or `EN` satisfies `InputCheckExit` and terminates the block.** For `E`: `StringCompare` fails on the length test (1 vs 3), but `StringStartsWith` compares `min(1,4) = 1` character, `'E'` vs `'E'`, and returns true (`src/pflotran/string.F90:452-459`).

Conversely `ENDIF` does *not* terminate: `StringCompare` fails (5 vs 3), and `StringStartsWith` compares 4 characters, failing at `'I'` vs `'_'`.

This is almost certainly unintended. It is stated here because a parser that models termination as "exactly `/`, `END`, or `END_*`" will differ from PFLOTRAN on the pathological input, and because it explains the `!geh:` comment at `src/pflotran/input_aux.F90:1522-1523` where the author already fought this comparison once.

---

## 7. Comment characters

> **Question.** We observe both `#` and `!` starting comments, including inline after a value. Confirm, and state precisely where a comment may begin.

**CONFIRMED.** Both characters are comment introducers, and both work at any column.

| Position | Implementation | Line |
|---|---|---|
| Whole-line, at the first non-blank character | `if (input%buf(1:1) == '#' .or. input%buf(1:1) == '!') cycle` | `src/pflotran/input_aux.F90:797` |
| Anywhere else in the line (inline) | truncate-at-first-occurrence loop | `src/pflotran/input_aux.F90:854-864` |

Precise statement of the rule:

- A comment begins at the **first `#` or `!` character on the line**, counted after leading whitespace and tabs have been left-justified away by `StringAdjustl` (`src/pflotran/input_aux.F90:786`, `src/pflotran/string.F90:503-534`).
- No whitespace is required before the comment character. `0.5#comment` truncates to `0.5`.
- The two characters are **exactly equivalent**; there is no distinction of any kind between them.
- The truncation is **quote-blind and escape-blind**. There is no exception for text inside single quotes, and the backslash is not an escape character in this scan. A filename or path containing `#` or `!` will be silently cut at that character, and the truncated remainder will then usually fail as a missing-file error rather than as a comment error.
- There is no block-comment syntax, and no line-continuation syntax. (`&` is Fortran source continuation inside `.F90` files, not deck syntax.)

---

## 8. Dynamic-key blocks: when the key is data, not a keyword

> **Question.** Inside `MINERAL_KINETICS`, each mineral NAME opens a sub-block — the key is data. Find that loop. Which other blocks behave this way?

This shape is real and is a distinct grammar production. It is documented in detail, with the `MINERAL_KINETICS` read loop and the enumeration of other dynamic-key blocks, in the companion file **`conditions_regions_strata.md`**, which also covers `CONSTRAINT`'s positional data rows.

The reader-level point belongs here: **nothing in `input_aux.F90` knows about dynamic keys.** They are implemented in exactly the same way as a fixed-keyword block — the block reader simply uses the token it read as *data* (a name to look up or store) instead of feeding it to a `select case`. There is no syntactic marker distinguishing the two, so a parser cannot tell a dynamic-key block from a fixed-keyword block without knowing the block's identity in advance.

---

## 9. The reader API

The complete public surface of `input_aux.F90` is declared at `src/pflotran/input_aux.F90:126-156`. The parts a deck author or parser cares about:

### 9.1 Line and token acquisition

| Routine | Purpose | Line |
|---|---|---|
| `InputReadPflotranString(input,option)` | fetch next significant line into `input%buf` | `:720-753` |
| `InputReadCard(input,option,word[,push_to_log])` | read next token as a keyword **and log it** | `:886-911` |
| `InputReadWord(input,option,word,return_blank_error)` | read next token into a 32-char word | `:1106-1125` |
| `InputReadNChars(input,option,chars,n,return_blank_error)` | read next token into an `n`-char buffer | `:1185-1208` |
| `InputReadFilename(input,option,filename)` | read a token as a filename, prepending the deck path | `:1293-1317` |
| `InputReadQuotedWord(input,option,word,return_blank_error)` | read a `'`-delimited token | `:1321-1340` |
| `InputReadInt(input,option,int)` | read next token as an integer | `:458-488` |
| `InputReadDouble(input,option,double)` | read next token as a real | `:592-624` |
| `InputReadNDoubles(input,option,array,n)` | read `n` reals, aborting on first failure | `:667-689` |
| `InputCountWordsInBuffer(input,option)` | **consume and count** remaining tokens | `:2776-2801` |

Numeric parsing is delegated to Fortran's own list-directed `read` (`read(word,*,iostat=...) int` at `:484`; `... double` at `:618`). So the accepted numeric syntax is Fortran's: `1.0`, `1e-7`, `1d-7`, `1.04D-7`, `-999`, `.5` are all valid, and `d`/`D` exponents (ubiquitous in real decks) are handled natively. **`InputReadDouble` additionally rejects NaN explicitly** (`:619-620`):

```fortran
! catch NaNs
if (double /= double) input%ierr = INPUT_ERROR_DEFAULT
```

Note `InputCountWordsInBuffer` is destructive — it reads tokens until failure (`:2795-2799`), leaving the buffer empty. Call sites that need the tokens afterwards must save and restore `input%buf` themselves.

**Oddity worth recording:** `InputReadCard`'s optional `push_to_log` argument has no effect. Both branches of the `if (present(push_to_log))` test call `InputPushCard` identically (`src/pflotran/input_aux.F90:905-909`). Call sites that pass `PETSC_FALSE` (e.g. `src/pflotran/factory_subsurface_read.F90:1070`) do not get the suppression they appear to request.

### 9.2 Error handling on a malformed card

The pattern is uniformly *"attempt the read, then assert"*:

```fortran
call InputReadDouble(input,option,material_property%rock_density)   ! material.F90:377
call InputErrorMsg(input,option,keyword,error_str)                  ! material.F90:378
```

`InputErrorMsg1` (`src/pflotran/input_aux.F90:330-350`) is a **no-op unless `input%ierr` is set**. When set, it stores the two context strings and calls `InputErrorMsg2` (`:354-382`), which:

1. dumps the block breadcrumb, filename, and line number via `InputPrintKeywordLog(...,PETSC_TRUE)` (`:369`, implementation `:915-968`, filename at `:939-940`, line number at `:942-943`);
2. composes `While reading "<what>" under keyword: <where>.` (`:370-371`);
3. appends a hint about the 32-character limit when `ierr == INPUT_ERROR_KEYWORD_LENGTH` (`:373-376`);
4. calls `PrintErrMsg(option)` — **fatal, the run stops** (`:379`).

Related assertion helpers:

| Routine | Fires when | Message shape | Line |
|---|---|---|---|
| `InputReadStringErrorMsg` | a line fetch failed (usually EOF mid-block) | `While reading in string in "<block>".` | `:386-429` |
| `InputFindStringErrorMsg` | a sought top-level block is absent | `Card (<name>) not found in file.` | `:433-454` |
| `InputKeywordUnrecognized` | `case default` in a block dispatcher | `Keyword "<kw>" not recognized in <context>.` | `:2407-2461` |
| `InputCheckSupported` | keyword valid but wrong process-model combination | lists employed vs required process models | `:2465-2548` |
| `InputKeywordDeprecated` | renamed keyword used | `Keyword "<old>" has been deprecated. Please use "<new>" instead.` | `:2552-2572` |
| `InputCheckMandatoryUnits` | units omitted where `input%force_units` is set | `Missing units in <block>,<card>.` | `:2576-2601` |

All of these are **fatal**. PFLOTRAN does not accumulate deck errors; it stops at the first one.

### 9.3 How a default is applied when a card is absent

There are two distinct mechanisms, and they are easy to confuse.

**(a) Absent *card* → the object's constructor value stands.** Defaults are set in each module's `*Create()` / `*Init*()` routine, not in the reader. There is **no default table and no default declaration syntax in the deck**. Canonical example, `OptionFlowInitRealization` (`src/pflotran/option_flow.F90:127-186`):

```fortran
option%reference_pressure = 101325.d0     ! :143
option%reference_temperature = 25.d0      ! :144
option%reference_porosity = 0.25d0        ! :146
option%reference_saturation = 1.d0        ! :147
```

Any of these is overridden only if the corresponding top-level card appears — `REFERENCE_PRESSURE` (`src/pflotran/factory_subsurface_read.F90:1369`), `REFERENCE_TEMPERATURE` (`:1407`), `REFERENCE_POROSITY` (`:1414`), `REFERENCE_SATURATION` (`:1421`), and so on.

Where "no default" is the correct answer, the field is seeded with a sentinel: `UNINITIALIZED_INTEGER = -999` / `UNINITIALIZED_DOUBLE = -999.d0` (`src/pflotran/pflotran_constants.F90:299-300`), tested later by `Uninitialized()` (`src/pflotran/pflotran_constants.F90:399`, `:482`).

**(b) Absent *optional token on a present card* → `InputDefaultMsg`.** When a card's trailing token is optional, the call site tolerates the read error and then calls `InputDefaultMsg` (`src/pflotran/input_aux.F90:306-326`), which prints `"<what>" set to default value.` (`:320-321`) and then **clears the sticky flag**: `input%ierr = INPUT_ERROR_NONE` (`:323`). This is the *only* routine that routinely clears `input%ierr` mid-block, and it is what makes optional trailing units work (§10).

> **Parser consequence.** A deck is not self-describing. You cannot know a parameter's effective value from the deck alone when its card is absent; you must consult the owning module's `*Create`/`*Init` routine. The four `option_*.F90` files in scope for this topic — `option_flow.F90`, `option_transport.F90`, `option_checkpoint.F90`, `option_parameter.F90` — contain **no deck-reading code at all** (no `select case` over card strings, no `InputRead*` calls). They are pure state containers holding exactly these constructor defaults: `flow_option_type` (`src/pflotran/option_flow.F90:13`), `transport_option_type` (`src/pflotran/option_transport.F90:13`), `checkpoint_option_type` (`src/pflotran/option_checkpoint.F90:15`), `parameter_option_type` (`src/pflotran/option_parameter.F90:11`).

### 9.4 Keyword logging (the breadcrumb)

`option%keyword_logging` defaults to `PETSC_TRUE` (`src/pflotran/option.F90:426`), with screen echo off by default (`:427`) and switchable only from the command line, not the deck (`src/pflotran/factory_forward.F90:593`). The state is four fields plus a fixed map (`src/pflotran/option.F90:101-106`).

`InputPushCard` appends to `keyword_buf` (`src/pflotran/input_aux.F90:993-997`) and — notably — treats `SKIP`/`NOSKIP` as block delimiters for logging purposes (`:1004-1009`).

---

## 10. Optional trailing units, from the reader's side

The grammar production is: **`<CARD> <number> [<unit-token>]`**.

The reader-side implementation is `InputReadAndConvertUnits` (`src/pflotran/input_aux.F90:2605-2645`). Its three load-bearing steps:

- The unit token is fetched with `return_blank_error = PETSC_TRUE` (`:2628`), so a **missing token does set `ierr`**.
- That error is then **swallowed** by `InputDefaultMsg` (`:2642`), which prints `"<CARD> units" set to default value.` and clears `ierr` (`:323`).
- When the token is absent, `double_value` is **left completely unmodified** (the multiply at `:2637-2639` is in the other branch) — i.e. the number is taken to be already in the caller's declared internal units.

So: **omitting units is legal and near-silent, and means "no conversion".** The unit strings themselves, the conversion tables, and the failure modes are covered in `units_and_conversion.md`.

Two caveats a parser must respect:

1. `input%force_units` (`src/pflotran/input_aux.F90:24`, default `PETSC_FALSE` at `:196`) can make a missing unit fatal via `InputCheckMandatoryUnits` (`:2576-2601`).
2. Not every units-bearing card goes through `InputReadAndConvertUnits`. Some read the unit token manually and call `UnitsConvertToInternal` directly, and those are **mandatory**, not optional — e.g. `TIME`/`FINAL_TIME` (`src/pflotran/factory_subsurface_read.F90:2287-2296`), where the unit token is read at `:2292` and the immediately following `InputErrorMsg` at `:2293` makes omission fatal, with an explanatory comment at `:2288-2289` (*"cannot use InputReadAndConvertUnits here because we need to store the units"*).

---

## 11. `DBASE_VALUE` — a numeric slot that is not a number

**This section is the single largest hazard for a parser that rewrites numeric values.**

Before parsing a token as an integer or a real, `InputReadInt1` / `InputReadDouble1` first check whether a database is loaded and, if so, whether the buffer begins with the literal `DBASE_VALUE` (`src/pflotran/input_aux.F90:476-478`, `:610-612`):

```fortran
found = PETSC_FALSE
if (associated(dbase)) then
  call InputParseDbaseForDouble(input%buf,double,found,option,input%ierr)
endif

if (.not.found) then
  call InputReadWord(input%buf,word,PETSC_TRUE,input%ierr)
  ...
```

`InputParseDbaseForDouble` (`src/pflotran/input_aux.F90:2193-2227`) saves the buffer, reads one token, and compares it case-insensitively against `'DBASE_VALUE'` (`:2212`, `:2217`, via `StringCompareIgnoreCase`, `src/pflotran/string.F90:224-263`). On a match it reads a second token as a key and looks it up (`:2218-2219`); on a miss it **restores the buffer** so the normal numeric path proceeds (`:2224`).

So all three of these are valid in a slot the deck grammar calls "a real number":

```
PERM_ISO 1.d-12
PERM_ISO DBASE_VALUE perm_key
PERM_ISO dbase_value perm_key        # keyword match is case-insensitive
```

The same applies to integers (`InputParseDbaseForInt`, `:2155-2189`) and to **words**, including names used as cross-references (`InputParseDbaseForWord`, `:2231-2269`, reached via `InputReadCardDbaseCompatible`, `:1151-1181`).

The database itself is a separate ASCII file named by the `DBASE_FILENAME` card (`src/pflotran/factory_subsurface_read.F90:771`) and parsed by `InputReadASCIIDbase` (`src/pflotran/input_aux.F90:1982-2151`). Its format: each line is `<object_name> <value_1> <value_2> ... <value_N>`, one column per realization; the column used is `option%id` (`:2053-2063`). Object names must be shorter than 32 characters (`:2020-2024`) and every row must have the same number of columns (`:2112-2124`). The value's **type** is inferred per row from the selected column by `StringIntegerDoubleOrWord` (`:2127`), sorting entries into three parallel tables (`:2129-2144`).

> **Parser requirement.** Before rewriting a numeric token, check whether the token at that position is the literal `DBASE_VALUE` (any case). If it is, the value lives in the `DBASE_FILENAME` file, keyed by the *following* token, and rewriting in place is wrong.

---

## 12. `option.F90` and friends, briefly

`option.F90` (1546 lines) is a state container, not a reader. Its relevance here is confined to the keyword-logging fields of §5.4 and §9.4 (`src/pflotran/option.F90:101-106`, initialized `:426-431`). Everything the deck sets on `option` is written there by *other* modules' block readers.

The four satellite modules in scope are likewise pure state (§9.3), each one derived type plus a `Create` / `Init*` / `Destroy` trio, and **none contains a single `case('...')` over a deck keyword**. Worth stating explicitly because the names suggest otherwise: the cards populating `flow_option_type` live in `factory_subsurface_read.F90` and `condition.F90`, and the `CHECKPOINT` block populating `checkpoint_option_type` is read by `CheckpointRead` from `src/pflotran/factory_forward.F90:164`.

---

## 13. Grammar summary, in one place

Informal EBNF for the *lexical and structural* layer only. Card semantics are per-block and cannot be captured here (§5).

```
deck            := line*
line            := blank | comment_line | directive | card | terminator
blank           := WS*
comment_line    := WS* ('#'|'!') ANY*
directive       := 'EXTERNAL_FILE' WS filename       (* pushes a nested file *)
                 | 'SKIP' ... 'NOSKIP'               (* swallows enclosed lines *)
card            := token (WS_or_COMMA token)*  [ ('#'|'!') ANY* ]
terminator      := WS* ( '/' ANY*
                       | 'END'                        (* exact, case-sensitive *)
                       | 'END_' IDENT )
token           := ( ANY - (' ' | ',' | TAB) )+       (* backslash also ends it,
                                                         unless it is char 1 *)
quoted_token    := "'" ( ANY - "'" )* "'"             (* only where the call site
                                                         asks for it            *)
number          := <Fortran list-directed real or integer; d/D exponents ok>
                 | 'DBASE_VALUE' WS key              (* case-insensitive kw *)
value_with_unit := number [ WS unit_token ]           (* unit usually optional *)
```

Structural facts that no EBNF can express, and that a parser must hard-code:

- Block *entry* is a keyword recognized by the currently-executing reader; block *identity* determines the child keyword namespace (§5).
- Named blocks (`REGION`, `MATERIAL_PROPERTY`, `CHARACTERISTIC_CURVES`, `FLOW_CONDITION`, `CONSTRAINT`, …) carry their name as the **second token on the opening line**.
- The `SUBSURFACE` block does not accept `/` or `END`; only the literal card `END_SUBSURFACE` (§6.2).
- Nesting depth is capped at 20 (§5.4).
- The file is read in multiple rewind-and-seek passes (§5.5).

---

## 14. Checklist for a rewriting parser

Ordered by how badly getting it wrong will hurt.

1. **Maintain a block-context stack.** Mirror `option%keyword_log`. Never resolve a keyword without it (§5).
2. **Handle `DBASE_VALUE` before touching any number.** Check the token; if it matches (case-insensitively), the value is external (§11).
3. **Resolve `EXTERNAL_FILE` includes** before assuming a line offset is stable; the target parameter may live in another file (§2.2).
4. **Respect `SKIP`/`NOSKIP` regions** — text in them is invisible to PFLOTRAN and must be invisible to you (§3, step 7).
5. **Strip comments at the first `#` or `!`,** with no quoting exception, and preserve the stripped tail if you are rewriting in place (§7).
6. **Treat commas as whitespace** when locating the *n*th token on a line (§4.1).
7. **Preserve the optional trailing unit token.** Rewriting `0.5 h` as `0.75` changes the value by 3600× (§10).
8. **Do not exceed 32 characters** for any name or keyword you write, or 40 for a line-leading token (§4.3).
9. **Mode-qualify condition cards.** The `TYPE` sub-block under `FLOW_CONDITION` has a different card set per flow mode (§5.3c).
10. **Do not assume a value's default from the deck.** Absent cards fall back to constructor values in `*Create`/`*Init*` (§9.3).

---

## 15. Things this document could not establish from static reading

Stated plainly, per the honesty requirement.

- **`SKIP` / `NOSKIP` interaction with `EXTERNAL_FILE`.** The `SKIP` swallow-loop at `src/pflotran/input_aux.F90:818-846` performs its own bare `read` and does **not** call `InputPopExternalFile` on EOF, unlike the main loop at `:788-795`. Whether a `SKIP` that begins in a parent file and ends in an included file (or vice versa) behaves sensibly is not determinable from reading alone; it looks fragile, but no test was run.
- **The `E` / `EN` terminator artifact (§6.4)** is derived from the source of `StringStartsWith`, not observed at runtime. The reasoning is given in full so it can be checked, but it has not been executed.
- **Complete card catalogue.** Deliberately out of scope, and in any case not statically enumerable in one pass: 397 `InputKeywordUnrecognized` sites imply at least that many independent `select case` dispatchers, several of which are further conditioned on run-time mode.
- **Which cards are genuinely optional versus which merely fail late.** Optionality is expressed by the `return_blank_error` flag and by whether a follow-up `InputErrorMsg` is present. This is per-call-site and cannot be summarized; it must be checked at the specific card.
- **Whether `option%force_units` is ever set true in practice.** It is initialized `PETSC_FALSE` at `src/pflotran/input_aux.F90:196`; no deck card that sets it was located within this topic's scope.
