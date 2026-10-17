---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** core orchestration: `drivers/ecosim/`, `f90src/{Main,Ecosim_mods,Modelconfig,Modelpars,Mesh,Utils,Minimath,DebugTools}/`
**Last verified:** 2026-10-15
---

# Core orchestration and infrastructure

These modules implement no biogeochemistry. They read the runfile, lay out the grid, allocate every state array, initialise soil, plant and chemistry state once at the start, march the clock, call the process modules in a fixed hourly order, and tear down. The time loop itself lives in the standalone driver `drivers/ecosim/`; the library directories hold the pieces it calls.

## 1. Directories

| directory | files | role | key entry points |
|---|---|---|---|
| `drivers/ecosim/` | 2 | the standalone executable and its year/day/hour loop | `program main` (`ecosim.F90:1`), `readnamelist` (`EcoSIMAPI.F90:130`), `AdvanceModelOneYear` (`:343`), `Run_EcoSIM_one_step` (`:37`) |
| `f90src/Main/` | 2 | one-time setup and teardown | `InitModules` (`f90src/Main/InitEcoSIM.F90:15`), `DestructEcoSIM` (`f90src/Main/EcoSIMDesctruct.F90:10`) |
| `f90src/Ecosim_mods/` | 4 | allocation and start-year initialisation | `InitAlloc` (`f90src/Ecosim_mods/InitAllocMod.F90:65`), `starts` (`StartsMod.F90:73`), `startq` (`StartqMod.F90:34`), `starte` (`StarteMod.F90:39`), `set_ecosim_solver` (`StartsMod.F90:952`) |
| `f90src/Modelconfig/` | 5 | run-control switches, sizes, ids | `EcoSIMCtrlMod`, `EcoSIMConfig`, `EcoSIMSolverPar`, `ElmIDMod`, `TracerIDMod` |
| `f90src/Modelpars/` | 8 | parameter blocks and the global objects `pltpar`, `micpar` | `EcoSiMParDataMod`, `PlantBGCPars`, `MicBGCPars`, `NitroPars`, `MicrobeConfigMod`, `ChemTracerParsMod`, `SoluteParMod`, `TracerPropMod` |
| `f90src/Mesh/` | 2 | landscape mesh and linear ids | `SetMesh` (`f90src/Mesh/GridMod.F90:13`), `SetMeshATS` (`:132`), `get_col` (`:210`), `get_pft` (`:219`) |
| `f90src/Utils/` | 14 (+ C helpers, `readme.md`) | kinds, constants, clock, files, NetCDF, abort, timing, strings, tests | `endrun`, `namelist_to_buffer`, `etimer`, `timings` |
| `f90src/Minimath/` | 3 | safe arithmetic and small physics functions | `MiniMathMod`, `MiniFuncMod`, `LinearAlgebraMod` |
| `f90src/DebugTools/` | 1 | `lverb`-gated print helpers | `PrintInfo`, `DebugPrint` |

## 2. Pages

| page | covers |
|---|---|
| [main_orchestration.md](main_orchestration.md) | the driver, `InitModules`/`InitAlloc`, `DestructEcoSIM`, the year/day/hour loop, the hourly call order down to the plant, microbial, hydrothermal and balance calls, the start-year initialisers |
| [model_config.md](model_config.md) | every `/ecosim/` namelist member with effective default and readers; the other namelist groups; prescribed-phenology mode; `Modelconfig/` and `Modelpars/` file summaries |
| [grid_and_mesh.md](grid_and_mesh.md) | horizontal mesh and ids; the vertical layer indices `NU`, `NUM`, `MaxNumRootLays` (`NJ`), `NK`, `NL` and their conflicting descriptions; which root and balance loops use which bound |
| [utilities.md](utilities.md) | abort behaviour (exit status 0), the 4096-byte runfile buffer, the clock, timing, safe arithmetic, debug helpers |

## 3. The big picture

```
program main                                     drivers/ecosim/ecosim.F90:1
  namelist_to_buffer, readnamelist               ecosim.F90:77, :80
  SetMesh                                        :98    -> JX, JY, JZ=20, bounds
  InitModules                                    :100   -> InitAlloc and twelve subsystem inits
  readi                                          :103   -> site, topography, layer indices (NU, NJ, NK, NL)
  set_sim_type, get_sim_len, hist_htapes_build   :107-126
  for each forcing period:                       :140
    set_ecosim_solver(NPXS, NPYS, NCYC_LITR, NCYC_SNOW)  :141
    for each repeat, for each climate year:      :143-150
      AdvanceModelOneYear                        :156
        InitControlParms; [start year only] STARTS, STARTQ, STARTE
        ReadPlantInfo, ReadClimSoilForcing
        for each day: DAY, SetAnnualAccumlators
          for each hour: PrepHourlyWeather, Run_EcoSIM_one_step, history, restart
  DestructEcoSIM                                 :172
```

`Run_EcoSIM_one_step` (`drivers/ecosim/EcoSIMAPI.F90:37-128`) calls, in order: `HOUR1` (balance snapshot, radiation, fertiliser), `WATSUB` (soil water and heat), `MicrobeModel` (if `microbial_model`), `MLDataDiag` (if `lmicrobeMLdiag`), `PlantModel` (if `plant_model` and not `ldo_radiation_test`), `soluteModel` (if `soichem_model`), `TranspNoSalt`, `TranspSalt` (if `salt_model`), `EROSION`, `REDIST`, `DiagSoilGasPressure`, `EndCheckBalances`.

## 4. Invariants worth remembering

- **Start-year initialisation, not annual.** STARTS, STARTQ and STARTE run only when the year of the current clock stamp equals the year of `frectyp%ymdhs0` (`EcoSIMAPI.F90:410`, `:434`, `:441`), despite comments that say "every year". Plants are re-initialised at planting by `StartPlants` (`f90src/Plant_bgc/InitPlantMod.F90:38`).
- **Forcing year and model year are separate.** `frectyp%yearclm` indexes the climate file and `frectyp%yearcur` the model calendar (`ecosim.F90:151-152`); `forc_periods` triplets recycle forcing years.
- **`InitAlloc` is the only allocation entry point**; a new state type is wired in `InitAllocMod.F90` and destroyed in `EcoSIMDesctruct.F90`. `InitSOMBGC` must run first because it sizes `micpar`, which `InitPlantMorphSize` copies into `pltpar` (`InitAllocMod.F90:67-69`).
- **`micpar` and `pltpar` are the only parameter objects** (`f90src/Modelpars/EcoSiMParDataMod.F90:7-8`).
- **Defaults come from `readnamelist`, not from the module initialisers**, for every switch it re-assigns (`EcoSIMAPI.F90:195-264`); `disp_planttrait` is the one where they differ. `&bbgcforc` and `&Microbes` must be present in every runfile.
- **Every `endrun` exits with status 0** (`f90src/Utils/abortutils.F90:80-121`); check logs for `ENDRUN:`.
- **`JZ=20` and `JP=5` are compile-time limits** (`GridMod.F90:88`; `GridConsts.F90:22`).
- **Two default-off fix switches** exist on this branch: `guard_floor_dying_stand` and `conserve_root_clamp` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:41`, `:46`); a runfile that omits them reproduces the previous binary's behaviour.

## 5. What is not here

The ATS-coupled driver (`f90src/ATSUtils/`, `drivers/ATSEcoSIM/`) uses `SetMeshATS` and `startsim` and its own advance routine; see the APIs section. History and restart I/O (`f90src/IOutils/`) are in the I/O section. The balance checks are collected in [../balances_and_disturbances/mass_balance.md](../balances_and_disturbances/mass_balance.md).

## Calibration parameters

None owned by these pages.
