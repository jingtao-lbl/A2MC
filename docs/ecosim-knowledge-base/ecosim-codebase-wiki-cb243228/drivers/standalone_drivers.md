---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `drivers/mockbatch/`, `drivers/plantbgc/`, `drivers/tools/`
**Last verified:** 2026-10-15
---

# Standalone Drivers: Mock, Plant, Tools

These are the small programs in `drivers/`. None of them runs EcoSIM physics at column scale. `mockbatch` is the template the batch drivers follow, `plantbgc` is a placeholder built from that template, and `tools` holds command-line utilities for the input files, the timer, history and restart. They all end through `endrun` on error, which exits with status 0 (`f90src/Utils/abortutils.F90:99`, `:119`).

## 1. `drivers/mockbatch/`: the batch-driver template

| File | Lines | Contents |
|---|---|---|
| `drivers/mockbatch/mockdriver.F90` | 166 | `program main` (`:1-31`), `usage` (`:36-43`), `RunModel` (`:48-166`) |
| `drivers/mockbatch/MockMod.F90` | 95 | `getvarllen` (`:19-26`), `getvarlist` (`:30-52`), `runmock` (`:57-75`), `initmodel` |

Build target `mock.x` (`drivers/mockbatch/CMakeLists.txt:5-6`); the library form is commented out (`:12-13`).

The flow is the one `aquachem` and `boxsbgc` copy:

```fortran
program main                                   ! drivers/mockbatch/mockdriver.F90:1-31
  ! exactly one argument, else usage + endrun
  call namelist_to_buffer(namelist_filename, namelist_buffer)   ! :27
  call RunModel(namelist_buffer)                                ! :29
end program main

subroutine RunModel(namelist_buffer)            ! :48-166
  namelist /driver_nml/ model_name, case_id, hist_freq          ! :80
  nvars = getvarllen(); call getvarlist(...)                    ! :108
  call initmodel(nvars, ystates0l, err_status)                  ! :118
  ! timer%Init(namelist_buffer=...), hist%init(...)
  do
    call timer%update_time_stamp()
    call runmock(nvars, ystates0l, ystatesfl, err_status)       ! :143
    ! copy state, hist_wrap
    if(timer%its_time_to_exit()) exit                           ! :160
  enddo
  call hist%histrst('mockmodel', 'write', yymmddhhss)           ! :164
end subroutine RunModel
```

`runmock` copies the five state and five flux slots unchanged (`drivers/mockbatch/MockMod.F90:70-71`). `initmodel` seeds states with 0.01 and fluxes with 1e-5. The history names are `var1_con` ... `var5_con` (mol m-3) and `flx1_con` ... `flx5_con` (mol m-2 s-1). Every flux long name is `'flx1'` (`:41-50`).

To start a new box driver: copy the directory, rename the program and module, replace `runmock`, `initmodel`, `getvarllen` and `getvarlist`, and add the directory to `drivers/CMakeLists.txt`. The timer reads `/ecosim_time/` from the same buffer (`f90src/Utils/ecosim_time_mod.F90:240-267`). Without that group the driver runs two years of 1800 s steps (`:250-252`).

### 1.1 Building a new box driver from the template

| Step | File | What to change |
|---|---|---|
| 1 | copy `drivers/mockbatch/` to `drivers/<name>/` | new directory |
| 2 | `<name>/MockMod.F90` | rename the module; replace `getvarllen` (slot count), `getvarlist` (names, long names, units, state or flux type), `initmodel` (initial state), `runmock` (one step) |
| 3 | `<name>/mockdriver.F90` | `use` the new module; extend `/driver_nml/` if the model needs inputs; rename the history label passed to `histrst` |
| 4 | `<name>/CMakeLists.txt` | executable name in `add_ecosim_executable`, include directories of the libraries used |
| 5 | `drivers/CMakeLists.txt` | add `add_subdirectory(<name>)` (`drivers/CMakeLists.txt:1-8`) |
| 6 | runfile | `/driver_nml/` plus `/ecosim_time/` with `delta_time` matching the step the new model assumes |

The state persists between steps only because `RunModel` copies `ystatesfl` back into `ystates0l` after each call. The step routine must write every slot of `ystatesfl`, which is `intent(out)` in the template (`drivers/mockbatch/MockMod.F90:62`).

## 2. `drivers/plantbgc/`: placeholder

| File | Lines | Contents |
|---|---|---|
| `drivers/plantbgc/plantdriver.F90` | 165 | same structure as `mockdriver.F90`; `/driver_nml/` at `:79`; calls `runplant` (`:142`); history restart `'plantmodel'` (`:163`) |
| `drivers/plantbgc/PlantTestMod.F90` | 95 | module `PlantTestMod`: `getvarllen`, `getvarlist`, `initmodel`, `runplant` |

Between 2dea74d9 and cb243228 the module was renamed from `PlantMod.F90` / `module PlantMod` to `PlantTestMod.F90` / `module PlantTestMod`, and `plantdriver.F90` now `use`s `PlantTestMod` (`git diff 2dea74d9 cb243228 -- drivers/plantbgc`). The old name was the same as the model's own `module PlantMod` (`f90src/APIs/PlantMod.F90`); the new one is not. The body is still the mock template: `runplant` copies its state through. `drivers/plantbgc/CMakeLists.txt` builds both a library `plant_driver` (`:5-6`) and the executable `plant.x` (`:17-18`), and prepends `plant_driver` to `ECOSIM_LIBRARIES` (`:14-15`).

| Item | `mock.x` | `plant.x` |
|---|---|---|
| Module | `MockMod` | `PlantTestMod` |
| Step routine | `runmock` (`drivers/mockbatch/mockdriver.F90:143`) | `runplant` (`drivers/plantbgc/plantdriver.F90:142`) |
| `/driver_nml/` | `model_name`, `case_id`, `hist_freq` (`drivers/mockbatch/mockdriver.F90:80`) | same (`drivers/plantbgc/plantdriver.F90:79`) |
| Usage string | `usage: mockmodel namelist_filename` (`drivers/mockbatch/mockdriver.F90:42`) | `usage: plantmodel namelist_filename` (`drivers/plantbgc/plantdriver.F90:42`) |
| History restart label | `'mockmodel'` (`drivers/mockbatch/mockdriver.F90:164`) | `'plantmodel'` (`drivers/plantbgc/plantdriver.F90:163`) |
| Library target | commented out (`drivers/mockbatch/CMakeLists.txt:12-13`) | `plant_driver` (`drivers/plantbgc/CMakeLists.txt:5-6`) |

`plant.x` does not run the EcoSIM plant model. To exercise plant physics in isolation, use the full model with `microbial_model = .false.` and `soichem_model = .false.`, or SP mode (`ecosim_main.md` §2.6).

## 3. `drivers/tools/`: utilities

Nine executables are built (`drivers/tools/CMakeLists.txt:15-24`, `EcoATSTest.x` commented at `:23`) and installed (`:105-114`).

| Source | Executable | Arguments | What it does | Key calls |
|---|---|---|---|---|
| `ClimTransformer.F90` (274 lines) | `ClimTransformer.x` | `<file list> <output.nc> hour|day` (`drivers/tools/ClimTransformer.F90:50-52`) | Converts a list of text climate tables into one NetCDF climate file. Dimensions `year` (unlimited), `day` (366), `ngrid` (1) and, for hourly data, `hour` (24) (`:63-69`). Per-year site variables include `Z0G`, `IFLGW`, `ZNOONG`, `PHRG` (rain pH), `CN4RIG`, `CNORIG`, `CPORG`, `CALRG` (rain chemistry) (`:123-146`). | text readers, `ncd_defdim`, `ncd_defvar` |
| `ClimReader.F90` (32) | `ClimReader.x` | `<climate.nc> <year>` (`drivers/tools/ClimReader.F90:23-24`) | Reads record 1 of one year for layer 2 as a smoke test of the climate reader (`:26-29`) | `ReadClimNC(iyear, irec, L, atmf)` |
| `PlantManagementReader.F90` (81) | `PlantManagementReader.x` | `<namelist>` (`drivers/tools/PlantManagementReader.F90:38`) | Reads `/pft_mgmnt/` (`year0`, `yearf`, grid bounds, `pft_mgmt_in`, `NPS`, `lverb`, `nyears`, `:29`) and loops `ReadPlantManagementNC` over years (`:78`) | `InitPlantMngmtData` (`:52`), `ReadPlantManagementNC` |
| `SoilManagementReader.F90` (30) | `SoilManagementReader.x` | `<soil management file>` (`drivers/tools/SoilManagementReader.F90:20`) | Reads the soil management schedule for one year | `ReadManagementFiles(iyear)` (`:28`) |
| `SoilWarmReadTest.F90` (26) | `SoilWarmReadTest.x` | none | Configures a hard-coded warming string and tests years 2013-2020 with `check_warming_dates(year,1,1)` (`drivers/tools/SoilWarmReadTest.F90:17-25`). The main driver now calls `check_warming_year` instead (`drivers/ecosim/EcoSIMAPI.F90:453`). | `config_soil_warming` |
| `etimerTest.F90` (47) | `etimerTest.x` | `<namelist>` (`drivers/tools/etimerTest.F90:27`) | Reads `/ecosim_time/` with `year0 = 1984`, steps the clock, and tests `get_steps_from_ymdhs` (`:29-42`) | `etimer%Init`, `update_time_stamp` |
| `NamelistTest.F90` (134) | `NamelistTest.x` | none; reads the hard-coded file `example_nl` (`drivers/tools/NamelistTest.F90:26`) | Exercises an old control group `/ecosys_ctrl/` (`hist_config`, `sim_yyyymmdd`, `forc_year0`, `forc_periods(5)`, `NPXS`, `NPYS`, `continue_run`, `:17-18`). This is not the current `/ecosim/` format: `forc_periods` there has 15 elements. | |
| `HFileTest.F90` (122) | `HFileTest.x` | `<namelist>` with `/hist_nml/` (`drivers/tools/HFileTest.F90:25-29`) | Writes synthetic history samples without physics | `HistFileMod` |
| `restartTest.F90` (76) | `restartTest.x` | `<namelist>` with `/hist_nml/` (`drivers/tools/restartTest.F90:20-24`) | Writes a restart file through the model's restart writer | `restFile(flag='write')` (`:75`) |
| `GridReader.F90` (51) | not built | `<grid.nc>` (`drivers/tools/GridReader.F90:14`) | Opens a grid file and reads the grid bounds | `ncd_pio_openfile` (`:16`) |
| `EcoATSTest.F90` (34) | not built (`drivers/tools/CMakeLists.txt:23`) | none | `SetBGCSizes` then `Init_EcoSIM` (`drivers/tools/EcoATSTest.F90:11`, `:15`); superseded by `drivers/ATSEcoSIM/ATSEcoSIM_test.F90` | |
| `EcoATSTest_old.F90` (65) | not built | none | Older ATS test that fills the C structs by hand before `Init_EcoSIM` (`drivers/tools/EcoATSTest_old.F90:43`) | |

`ClimTransformer.x` is the one most users need: it produces the `clm_hour_file_in` / `clm_day_file_in` files the main driver reads. The climate pipeline downstream of that file is documented in `../io_and_forcing/forcing.md`.

### 3.1 Usage examples

```
# text climate tables -> NetCDF (exactly 3 arguments, else endrun; drivers/tools/ClimTransformer.F90:45-52)
./ClimTransformer.x  file_list.txt  site_climate.nc  hour
./ClimTransformer.x  file_list.txt  site_climate.nc  day

# read record 1 of 2012 from a climate file (drivers/tools/ClimReader.F90:23-29)
./ClimReader.x  site_climate.nc  2012

# management readers
./SoilManagementReader.x   soil_mgmt.nc          # drivers/tools/SoilManagementReader.F90:20
./PlantManagementReader.x  pft_mgmt.namelist     # drivers/tools/PlantManagementReader.F90:38

# timer, history, restart tests
./etimerTest.x     timer.namelist                # /ecosim_time/
./HFileTest.x      hist.namelist                 # /hist_nml/
./restartTest.x    hist.namelist                 # /hist_nml/
```

`ClimTransformer.x` checks the list file exists (`drivers/tools/ClimTransformer.F90:54-57`) and opens it from `./` (`:58-60`). The third argument selects the hourly (`hour`) or daily (`day`) layout; for `hour` an extra `hour` dimension of length 24 is defined (`drivers/tools/ClimTransformer.F90:69`).

### 3.2 Tool namelists

| Tool | Group | Members | Citation |
|---|---|---|---|
| `PlantManagementReader.x` | `/pft_mgmnt/` | `year0`, `yearf`, `NHW`, `NHE`, `NVN`, `NVS`, `pft_mgmt_in`, `NPS`, `lverb`, `nyears` | `drivers/tools/PlantManagementReader.F90:29` |
| `HFileTest.x`, `restartTest.x` | `/hist_nml/` | `hist_nhtfrq`, `hist_mfilt`, `hist_fincl1`, `hist_fincl2`, `hist_yrclose` (read by unit, not through the 4096-byte buffer) | `drivers/tools/HFileTest.F90:25-26`, `:29-48`; `drivers/tools/restartTest.F90:20` |
| `etimerTest.x` | `/ecosim_time/` | as in the main model | `f90src/Utils/ecosim_time_mod.F90:240-241` |
| `NamelistTest.x` | `/ecosys_ctrl/` | `hist_config`, `sim_yyyymmdd`, `forc_year0`, `forc_periods(5)`, `NPXS(5)`, `NPYS(5)`, `continue_run` (obsolete layout) | `drivers/tools/NamelistTest.F90:15-18` |

`HFileTest.x` and `restartTest.x` open their namelist file with `open(... newunit=fu)` and `read(unit=fu, nml=hist_nml)` (`drivers/tools/HFileTest.F90:38-48`). The 4096-byte limit does not apply to them, and a missing or unreadable file ends in `endrun`.

## 4. Shared behaviour

| Behaviour | Where it comes from | Consequence |
|---|---|---|
| Namelist path as the first argument; 4096-byte buffer | `namelist_to_buffer` (`f90src/Utils/fileUtil.F90:125-176`) | a file of 4096 bytes or more aborts (non-zero) |
| Timer group `/ecosim_time/` | `f90src/Utils/ecosim_time_mod.F90:240-267` | `&ecosim_time_nml` or any misspelling that still contains `ecosim_time` fails the read and calls `endrun` |
| `endrun` | `f90src/Utils/abortutils.F90:80-153` | prints `ENDRUN:`, bare `stop`, exit status 0 |
| History via `bhistMod` (batch drivers) or `HistFileMod` (tools) | `f90src/IOutils/bhistMod.F90`, `f90src/IOutils/HistFileMod.F90` | batch drivers write their own flat-vector tapes |

## Cross-references

- Main driver: `ecosim_main.md`.
- Batch drivers that follow the template: `aquachem.md`, `boxsbgc.md`.
- ATS test driver: `ats_coupling.md` §10.
- Input readers exercised by the tools: `../io_and_forcing/input_readers.md`.
