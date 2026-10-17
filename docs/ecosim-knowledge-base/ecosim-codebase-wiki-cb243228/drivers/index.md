---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `drivers/` (`ecosim/`, `ATSEcoSIM/`, `aquachem/`, `boxsbgc/`, `boxshared/`, `mockbatch/`, `plantbgc/`, `tools/`) and `f90src/ATSUtils/`
**Last verified:** 2026-10-15
---

# Drivers: Overview

EcoSIM has no single entry point. `drivers/` holds several Fortran `program`s, each linking a different subset of the component libraries, plus one bridge library (`f90src/ATSUtils/`) that lets the external ATS flow solver call EcoSIM as a column engine. `drivers/CMakeLists.txt` adds all eight subdirectories unconditionally (`drivers/CMakeLists.txt:1-8`): `ecosim`, `mockbatch`, `boxshared`, `aquachem`, `boxsbgc`, `plantbgc`, `tools`, `ATSEcoSIM`. The top-level `CMakeLists.txt` adds `f90src` and then `drivers` (`CMakeLists.txt:274-275`).

For calibration work only one of these matters: `ecosim.f90.x`, built from `drivers/ecosim/`. Everything A2MC runs for an EcoSIM case is that executable reading one runfile.

## Driver summary

| Driver directory | Executable | Program file | What it runs |
|---|---|---|---|
| `drivers/ecosim/` | `ecosim.f90.x` | `drivers/ecosim/ecosim.F90` | The full standalone model: namelist, grid, year, day and hour loops, all physics through `EcoSIMAPI` (see `ecosim_main.md`) |
| `drivers/ATSEcoSIM/` | `ATSEcoSIM_test.x` | `drivers/ATSEcoSIM/ATSEcoSIM_test.F90` | In-process exerciser of the ATS bridge with synthetic inputs (see `ats_coupling.md`) |
| `f90src/ATSUtils/` | library `ATSUtils_mods` | 8 files | The bridge ATS links against: `bind(C)` entry points `EcoSIM_Setup`, `EcoSIM_Advance`, `EcoSIM_Shutdown` (see `ats_coupling.md`) |
| `drivers/aquachem/` | `aquachem.x` | `drivers/aquachem/aquachem.F90` | One-box aqueous equilibria harness for the no-salt and salt solvers (see `aquachem.md`) |
| `drivers/boxsbgc/` | `boxsbgc.x` | `drivers/boxsbgc/batchsbgc.F90` | One-layer soil microbial BGC harness driven by a NetCDF forcing file (see `boxsbgc.md`) |
| `drivers/boxshared/` | library | `drivers/boxshared/ChemIDMod.F90` | The `cid_*` / `fid_*` state-index table shared by `aquachem` and `boxsbgc` |
| `drivers/mockbatch/` | `mock.x` | `drivers/mockbatch/mockdriver.F90` | Copy-through template for new batch drivers (see `standalone_drivers.md`) |
| `drivers/plantbgc/` | `plant.x` and library `plant_driver` | `drivers/plantbgc/plantdriver.F90` | Placeholder with the same template body; module now `PlantTestMod` (see `standalone_drivers.md`) |
| `drivers/tools/` | nine `.x` utilities | 12 source files | Climate-file converter, management-file readers, timer, history and restart round-trip tests (see `standalone_drivers.md`) |

## Full driver versus box drivers versus ATS

**Full column driver.** `ecosim.f90.x` reads the runfile into a 4096-byte buffer, parses the `/ecosim/`, `/bbgcforc/`, `/ecosim_time/`, `/Microbes/` and optional `/FixClimForc/` groups, builds the grid, and then loops forcing periods, years, days and hours. Each hour it calls the module-private `Run_EcoSIM_one_step` (`drivers/ecosim/EcoSIMAPI.F90:37-128`), which runs surface energy and water (`HOUR1`, `WATSUB`), soil microbes (`MicrobeModel`), plants (`PlantModel`), geochemistry (`soluteModel`), transport (`TranspNoSalt`, `TranspSalt`), erosion, state redistribution and the balance checks. Details: `ecosim_main.md`.

**Box drivers.** `aquachem.x`, `boxsbgc.x`, `mock.x` and `plant.x` share one pattern: one command-line argument (the namelist path), `namelist_to_buffer`, a `/driver_nml/` group, a flat state vector `ystates0l(1:nvars)` / `ystatesfl(1:nvars)` indexed by `cid_*` and `fid_*` integers, a `histf_type` history tape, and a `do ... enddo` loop that ends when `timer%its_time_to_exit()` is true. They have no grid, no climate file and no hourly orchestrator. Each driver's timer reads the same `/ecosim_time/` group as the full model (`f90src/Utils/ecosim_time_mod.F90:240-241`), with the same defaults: `delta_time = 1800` s, `stop_n = 2`, `stop_option = 'nyears'` (`:250-252`).

**ATS coupling.** ATS owns the time loop and calls three C-bound subroutines in `f90src/ATSUtils/ecosim_wrappers.F90`. Under ATS, EcoSIM runs the surface energy and snow balance per column, and, when ATS passes `pheno_bool = .true.`, the prescribed-phenology plant uptake path. Microbes and geochemistry are switched off (`f90src/ATSUtils/ATSEcoSIMInitMod.F90:56-60`). The plant trait table is never read in ATS mode; the traits are hard-coded (see `ats_coupling.md`).

## How a run ends (all drivers)

Every `endrun` call, whichever overload, prints `ENDRUN:` and then executes a bare `stop` (`f90src/Utils/abortutils.F90:99`, `:119`, `:151`), so the process exits with status 0. NetCDF errors (`f90src/Utils/ncdio_pio.F90:463-466`, `check_ret`), namelist read errors, balance-check failures and bad `stop_option` values all go through `endrun`. Only three paths give a non-zero status: `abort()` in `namelist_to_buffer` (`f90src/Utils/fileUtil.F90:150`, `:173`), `error stop` in the timer module (`f90src/Utils/timings.F90:78`), and a floating-point trap, because the GNU build compiles with `-ffpe-trap=invalid,zero,overflow` (`cmake/Modules/set_up_compilers.cmake:79`). A scheduler state of COMPLETED with exit code 0 is therefore not evidence of a good run. `ecosim_main.md` §6 gives the full list and the run evidence.

## Build switches that affect the drivers

| Switch | Where | Effect |
|---|---|---|
| `ATS_ECOSIM` | `CMakeLists.txt:173-199` | Adds `-fPIC` to the C, C++ and Fortran flags and `-g -O0 -fbacktrace -fbounds-check` to Fortran (`:194-196`), and points NetCDF and HDF5 at `${TPL_INSTALL_PREFIX}` (the Amanzi TPL install, `:28`, `:183-192`). `f90src/ATSUtils/` and `drivers/ATSEcoSIM/` are built either way. |
| GNU Fortran flags | `cmake/Modules/set_up_compilers.cmake:61`, `:79-82` | `-fdefault-real-8 -fdefault-double-8` and `-ffpe-trap=invalid,zero,overflow`. Underflow was removed from the trap list on the fork (comment block `:62-78`). |

## Call graph of the full driver

```
PROGRAM main                                        drivers/ecosim/ecosim.F90:1-175
  namelist_to_buffer                                f90src/Utils/fileUtil.F90:125-176   (4096 bytes)
  readnamelist                                      drivers/ecosim/EcoSIMAPI.F90:130-340
    etimer%Init -> ReadNamelist (/ecosim_time/)     f90src/Utils/ecosim_time_mod.F90:139-304
    config_soil_warming, config_fire, ReadMicrobeNamelist (/Microbes/)
  SetMesh, InitModules (ReadPlantTraitTable if plant_model and not ATS), readi
  write_modelconfig, set_sim_type, get_sim_len, etimer%update_sim_len
  hist_htapes_build, get_clm_years
  DO period / repeat / forcing year                 drivers/ecosim/ecosim.F90:140-167
    AdvanceModelOneYear                             drivers/ecosim/EcoSIMAPI.F90:343-571
      InitControlParms, STARTS*, ReadPlantInfo, ReadClimSoilForcing, STARTQ*, STARTE*  (* first year)
      DO day:  DAY, SetAnnualAccumlators
        DO hour: [restart read at ymdhs0] [fast-forward while lskip_loop]
          PrepHourlyWeather
          Run_EcoSIM_one_step                       drivers/ecosim/EcoSIMAPI.F90:37-128
            HOUR1, WATSUB, MicrobeModel, PlantModel, soluteModel,
            TranspNoSalt, TranspSalt, EROSION, REDIST, DiagSoilGasPressure, EndCheckBalances
          hist_update, hist_update_hbuf, update_time_stamp
          hist_htapes_wrapup, restFile('write') if rstwr
  regressiontest (optional), DestructEcoSIM
```

## Source inventory with sizes

| File | Lines |
|---|---|
| `drivers/ecosim/ecosim.F90` | 175 |
| `drivers/ecosim/EcoSIMAPI.F90` | 668 |
| `drivers/ecosim/CMakeLists.txt` | 58 |
| `drivers/ATSEcoSIM/ATSEcoSIM_test.F90` | 181 |
| `f90src/ATSUtils/ATSCPLMod.F90` | 375 |
| `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90` | 382 |
| `f90src/ATSUtils/ATSEcoSIMInitMod.F90` | 158 |
| `f90src/ATSUtils/ATSUtilsMod.F90` | 47 |
| `f90src/ATSUtils/BGC_containers.F90` | 225 |
| `f90src/ATSUtils/SharedDataMod.F90` | 209 |
| `f90src/ATSUtils/c_f_interface_module.F90` | 187 |
| `f90src/ATSUtils/ecosim_wrappers.F90` | 126 |
| `drivers/aquachem/aquachem.F90` | 173 |
| `drivers/aquachem/AquachemMod.F90` | 443 |
| `drivers/aquachem/AquaSaltChemMod.F90` | 1003 |
| `drivers/boxsbgc/batchsbgc.F90` | 240 |
| `drivers/boxsbgc/batchmod.F90` | 1764 |
| `drivers/boxsbgc/ChemMod.F90` | 272 |
| `drivers/boxsbgc/ForcTypeMod.F90` | 503 |
| `drivers/boxsbgc/MicIDMod.F90` | 109 |
| `drivers/boxshared/ChemIDMod.F90` | 392 |
| `drivers/mockbatch/mockdriver.F90` | 166 |
| `drivers/mockbatch/MockMod.F90` | 95 |
| `drivers/plantbgc/plantdriver.F90` | 165 |
| `drivers/plantbgc/PlantTestMod.F90` | 95 |
| `drivers/tools/*.F90` (12 files) | 26 to 274 each |

## Changes since the 2dea74d9 pin

| File | Change |
|---|---|
| `drivers/ecosim/EcoSIMAPI.F90` | New `/ecosim/` members `LMacPoreOff`, `llignification`, `hist_fincl3`, `lmicrobeMLdiag`, `do_timing_detail`, `lcoarseroot`, `guard_floor_dying_stand`, `conserve_root_clamp` (`:160-182`); `InitControlParms` every year (`:407`); `ReadClimSoilForcing` moved after `ReadPlantInfo` (`:420-430`); warming reference loaded whenever any day of the year is warmed (`:453-457`); `MLDataDiag` hook (`:66`); per-step timers |
| `drivers/ecosim/ecosim.F90` | `nmlfile` length 36 -> 256 (`:43`); timer initialisation and finalisation (`:89-92`, `:131-134`, `:173`) |
| `drivers/boxsbgc/{batchmod,ForcTypeMod}.F90` | microbial group count split into heterotroph and autotroph counts; forcing file needs two new dimensions |
| `drivers/plantbgc/` | `PlantMod.F90` renamed `PlantTestMod.F90` |
| `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90` | comments only |

## Choosing a driver

| Goal | Use |
|---|---|
| Calibrate or evaluate a site | `ecosim.f90.x` with a runfile under 4096 bytes |
| Check a geochemistry edit on a fixed box | `aquachem.x` in no-salt mode (salt mode not usable at cb243228) |
| Check a microbial-library edit at fixed 298 K, 0.65 saturation | `boxsbgc.x`, with a forcing file that defines the two group-count dimensions |
| Convert text climate tables to the NetCDF the model reads | `ClimTransformer.x` |
| Smoke-test a management or climate file | `PlantManagementReader.x`, `SoilManagementReader.x`, `ClimReader.x` |
| Couple to ATS | link `ATSUtils_mods`; test with `ATSEcoSIM_test.x` |

## What is not in this section

The physics routines the drivers call (`HOUR1`, `WATSUB`, `MicrobeModel`, `PlantModel`, `TranspNoSalt`, `TranspSalt`, `EROSION`, `REDIST`) are documented in their own sections of this wiki. The geochemistry solver called by `soluteModel` is documented in `../geochem/`. The runfile readers are covered in more depth in `../io_and_forcing/input_readers.md`, and the history and restart writers in `../io_and_forcing/history_and_restart.md`.

## Pages

- `ecosim_main.md`: `ecosim.F90` and `EcoSIMAPI.F90`, including the namelist reference, run length, restart cadence, the switches `guard_floor_dying_stand`, `conserve_root_clamp` and `ldo_sp_mode`, and exit status.
- `ats_coupling.md`: the ATS bridge, what ATS sets in place of the plant trait table, and known coupling defects.
- `aquachem.md`: the aqueous chemistry harness.
- `boxsbgc.md`: the one-layer soil BGC harness.
- `standalone_drivers.md`: `mockbatch`, `plantbgc`, and `tools`.

## Checklist before launching `ecosim.f90.x`

1. Runfile under 4096 bytes, including comments (`f90src/Utils/fileUtil.F90:25`).
2. `/ecosim_time/` present, with `delta_time = 3600.` and `stop_n` equal to the `forc_periods` total (`f90src/Utils/ecosim_time_mod.F90:1086-1093`).
3. `&bbgcforc /` present, even if empty.
4. Every input path in `/ecosim/` exists. A missing plant trait file or NetCDF variable ends in `ENDRUN` with exit status 0.
5. Ensemble cases that may kill the stand: `guard_floor_dying_stand = .true.` (`ecosim_main.md` §2.5).
6. After the run, check stdout for `ENDRUN:` and the last history time sample. Do not rely on `rc` or the scheduler state.

## Quick facts for a calibrator

| Question | Answer at cb243228 | Citation |
|---|---|---|
| Which executable does A2MC run? | `ecosim.f90.x`, one runfile argument | `drivers/ecosim/ecosim.F90:75-80` |
| Largest runfile that can be read | 4095 bytes; 4096 or more aborts | `f90src/Utils/fileUtil.F90:25`, `:143-150` |
| Default run length without `/ecosim_time/` | 2 years (`stop_n = 2`), whatever `forc_periods` says | `f90src/Utils/ecosim_time_mod.F90:251-252`, `:1086-1093` |
| Is a restart written at the end? | Yes, always (`nlend` is ORed in) | `f90src/Utils/ecosim_time_mod.F90:353` |
| Calendar | Gregorian: 366-day leap years | `f90src/Utils/ecosim_time_mod.F90:652-658` |
| Exit status of an `ENDRUN` | 0 | `f90src/Utils/abortutils.F90:119` |
| Where output files go | the working directory (`./<case>.ecosim.h*.nc`, `./<case>.ecosim.r.*.nc`); `<case>_outputs/` only receives timing files | `f90src/IOutils/HistFileMod.F90:2183`, `f90src/IOutils/RestartMod.F90:10161-10162`, `f90src/Utils/timings.F90:54-56` |
