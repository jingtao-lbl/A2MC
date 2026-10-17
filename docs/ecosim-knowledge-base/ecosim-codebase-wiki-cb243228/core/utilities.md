---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/Utils/`, `f90src/Minimath/`, `f90src/DebugTools/` (summary level)
**Last verified:** 2026-10-15
---

# Utilities, small maths and debug helpers

These modules hold no science. They matter to a calibrator for four reasons: how an abort ends the process, how big the runfile may be, how the clock and timing work, and which "safe" arithmetic silently clamps values. Everything else is summarised briefly.

## 1. Directory contents

| directory | Fortran files | other files |
|---|---|---|
| `f90src/Utils/` | 14: `EcoSimConst`, `ModelStatusType`, `StringToolsMod` (renamed from `StrToolsMod` since `2dea74d9`), `TestMod`, `UnitMod`, `abortutils`, `data_const_mod`, `data_kind_mod`, `ecosim_log_mod`, `ecosim_time_mod`, `fileUtil`, `ncdio_pio`, `shr_infnan_mod`, `timings` | `clock.c`, `getfilename.c`, `dtypes.h`, a committed object `clock.o`, and a new `readme.md` |
| `f90src/Minimath/` | 3: `LinearAlgebraMod`, `MiniFuncMod`, `MiniMathMod` | |
| `f90src/DebugTools/` | 1: `DebugToolMod` | |

## 2. How the model stops: `abortutils`

`endrun` is a generic interface over `endrun_vanilla(msg)`, `endrun_line(msg,line)` and `endrun_globalindex(...)` (`f90src/Utils/abortutils.F90:19-23`). All three write `ENDRUN:` and the message to unit `iulog = 6` (`:16`) and then execute a plain `stop` (`:80-101`, `:104-121`). A plain `STOP` ends the program normally, so with the usual compilers an aborted EcoSIM run returns exit status 0. A batch scheduler will report such a run as completed. Detect aborts from the `ENDRUN:` line in standard output, from the balance dump files (`fort.110`, `fort.111`, `fort.888`, see [../balances_and_disturbances/mass_balance.md](../balances_and_disturbances/mass_balance.md)), or from history tapes that stop early. `abortutils` also provides the generic `destroy` deallocators used by every `Destruct*` routine (`:24-32` onward).

## 3. Runfile buffer: `fileUtil`

`ecosim_namelist_buffer_size = 4096` (`f90src/Utils/fileUtil.F90:25`) and `datestrlen = 14` (`:27`). `namelist_to_buffer` (`:125-170`) reads the runfile as one unformatted stream into the buffer and requires the read to hit end of file (`:143-150`); a runfile longer than 4096 bytes therefore aborts with an I/O error, and a shorter one is accepted, with everything after the last `/` blanked (`:155-158`). The same module exports `file_exists`, `open_safe`, `getavu`/`relavu` unit management and a second `continue_run` flag (`:26`) that is separate from the namelist member of the same name in `EcoSIMCtrlMod` and is used only by `bhistMod` (`f90src/IOutils/bhistMod.F90:119`, `:338`).

## 4. Clock: `ecosim_time_mod`

`ecosim_time_type` holds the simulation clock (`etimer`, declared in `f90src/Modelconfig/EcoSIMCtrlMod.F90:111`). `Init` (`f90src/Utils/ecosim_time_mod.F90:139`) sets defaults (`delta_time = 1800` s, `stop_n = 2`, `stop_option = 'nyears'`, `:250-252`) and reads `/ecosim_time/` only if that string occurs in the buffer (`:240-262`). The driver advances it with `update_time_stamp` (`:420-493`) once per model hour and queries `its_time_to_exit` (`:403-417`), `its_a_new_year` (`:748-755`) and `get_days_cur_year` (`:652`). The calendar is a real Gregorian calendar: the day loop runs to `get_days_cur_year()` (365 or 366) and `DAY` uses `isLeap` for the equation of time (`f90src/Modelforc/DayMod.F90:66-72`).

## 5. Timing: `timings` (rewritten since `2dea74d9`)

`f90src/Utils/timings.F90` (207 lines) is wall-clock profiling for the serial driver. Public: `timer_launch_label`, `init_timer(outdir, detail, run_start)`, `start_timer`, `end_timer(name, stamp)`, `end_timer_loop`, `flush_timer_detail`, `finalize_timer`, `timer_elapsed` (`:27-28`). `init_timer` creates `<outdir>/timing/` and writes `summary.csv` (`:54-58`), plus `timing/time-<launch>.txt` per-step records when `do_timing_detail` is set. Regions are inclusive and accumulation is not thread safe (`:2-3`). The driver wraps every major call of `AdvanceModelOneYear` and `Run_EcoSIM_one_step` in `start_timer`/`end_timer` when `do_timing` is true (for example `drivers/ecosim/EcoSIMAPI.F90:46-51`). The usage is documented in `f90src/Utils/readme.md`.

## 6. Constants and kinds

- `data_kind_mod`: `DAT_KIND_R8 = selected_real_kind(12)` (`f90src/Utils/data_kind_mod.F90:9`), imported everywhere as `r8`.
- `EcoSimConst` (60 lines): physical constants and a few model thresholds, for example `secsphour`, `cpw`, `TC2K = 273.15`, `PICON`, `LtHeatIceMelt = 333.55`, `EvapLHTC = 2465.0`, `RGASC`, `OMCMassFrac = 0.55`, `FORGC = 1e5` (minimum SOC for organic soil, used by soil fire), `VolMaxSoilMoist4Fire = 1.0`, `FrcAsCH4byFire = 0.01`, `DENSICE = 0.92` (`f90src/Utils/EcoSimConst.F90:8-47`). Because `VolMaxSoilMoist4Fire` is 1.0, the soil-fire moisture test `THETW_vr > VolMaxSoilMoist4Fire` (`f90src/Disturbances/SoilDisturbMod.F90:85`) never stops combustion.
- `UnitMod`: the `units` object with `Celcius2Kelvin`, `Kelvin2Celcius`, `get_SecondsPerDay` and others; initialised in `InitModules` (`f90src/Main/InitEcoSIM.F90:39`).
- `data_const_mod`: shared constants including `DAT_CONST_SPVAL = 1.0e30` and `DAT_CONST_ISPVAL = -999` (`f90src/Utils/data_const_mod.F90:62-63`), the history fill values (`spval`).

## 7. Safe arithmetic: `MiniMathMod`

`MiniMathMod` (727 lines) is used throughout the physics. The functions a reader most often meets:

| function | line | behaviour |
|---|---|---|
| `safe_adb(a,b)` | `f90src/Minimath/MiniMathMod.F90:64-80` | returns 0 when `abs(b) < tiny_val = 1e-12` (`:58`), else `AZERO(a/b)`; so a near-zero denominator yields 0, not an error. The plant and transport balance checks use it for the relative error, which is why a collapsing denominator can make a relative test read as small |
| `AZMAX1`, `AZMIN1` | interface `:44-48` | `max(x,0)`, `min(x,0)` with variants; `AZMAX1` is the clamp that removes negative pools (for example the root structural clamp in `GrowFibrous1stRootAxes`) |
| `isclose(a,b)` | `:393-414` | tolerance comparison used for `THIN_pft==0` tests in harvest code |
| `fixnegmass(val,refcon)` | `:464-478` | sets small negative values to zero: below 0 and above `-1e-5` (or above `min(-1e-3*refcon,-1e-5)` when `refcon` is given); larger negatives are returned unchanged |
| `sfexp` | `:697-711` | overflow-safe exponential |
| `isLeap`, `vapsat`, `AZERO`, `fixEXConsumpFlux`, `symmetric_flux_limiter`, `flux_mass_limiter`, `addone` | public list `:15-57` | leap year, saturation vapour pressure, zero-threshold, flux limiters, sequential id helper (used by `InitTracerIDs`) |

`MiniFuncMod` (239 lines) holds small closed-form physics: water film thickness (`:14`), tortuosity (`:82`, `:91`), aqueous and gas diffusivity temperature factors (`:46`, `:64`), effective solute diffusivity (`:102`), day length (`:154`), solar declination (`:181`), the equation of time (`:202`), and a new `Harmonicmean_safe` (`:30`). `LinearAlgebraMod` provides `sparse_gemv` and `taxpy` (`f90src/Minimath/LinearAlgebraMod.F90:15-16`).

## 8. NetCDF and history I/O helpers

`ncdio_pio` (3295 lines) is a serial NetCDF wrapper with the `ncd_pio_openfile`, `ncd_getvar` (generic over types and ranks), `check_var`, `get_dim_len` and define/put routines. A bare `ncd_getvar` on a missing variable aborts; optional reads use `check_var` first (for example the `SPOSC` read in `f90src/Modelpars/NitroPars.F90:363-364`). `shr_infnan_mod` (generated code) provides NaN and Inf tests; `ecosim_log_mod` provides `shr_log_errMsg`.

## 9. Strings, tests, status

- `StringToolsMod` (439 lines): `parse_var_val_string` (the `key[value];...` parser used by `warming_exp`, `f90src/Disturbances/EcosysWarmingMod.F90:216`), `are_strings_equal_icase`, `extract_number_and_unit`, `is_substring_present`, `to_lower_string`, `count_delimited_items`, `string_compaction` (`f90src/Utils/StringToolsMod.F90:9-15`).
- `TestMod` (340 lines): the regression-test object `regression` (`Init` `:60`, `ReadNamelist` `:81`, `CheckInput` `:146`, `OpenOutput` `:166`) used by `regressiontest` (`drivers/ecosim/EcoSIMAPI.F90:574-644`), which writes NH4 uptake, aqueous O2, liquid water and soil temperature for the first 12 layers.
- `ModelStatusType` (86 lines): a small status/message object (`create_model_status_type` `:24`, `set_msg` `:44`, `check_status` `:59`).

## 10. Debug helpers: `DebugToolMod`

`f90src/DebugTools/DebugToolMod.F90` (103 lines) exports `PrintInfo(message)`, which writes only when `lverb` is true (`:32-37`); the generic `DebugPrint` over real arrays, real scalars and integers, each returning immediately when `lverb` is false (`:16-21`, `:41-89`); `do_debug()` returning `lverb` (`:25-30`); and `GetSoilWaterMass(NY,NX)`, the soil water plus ice mass from `NU` to `NL` (`:92-102`). `lverb` is set from the namelist member `lverbose` and can be switched on for one day with `idebug_day`/`idebug_year` (`drivers/ecosim/EcoSIMAPI.F90:300`, `:469-473`). Almost every routine opens with `call PrintInfo('beg '//subname)`, so a verbose run produces a nested call trace.

## Calibration parameters

None. These modules hold no calibration parameter; `EcoSimConst` thresholds are compile-time constants.
