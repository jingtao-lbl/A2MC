---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/` + `drivers/` (full repository, overview level)
**Last verified:** 2026-10-15
---

# Overview

## What EcoSIM is

EcoSIM describes itself as "A biogeochemical modeling library spins off the ecosys model" (`README.md:3`). The repository builds a Fortran library from `f90src/` and several executables under `drivers/` that link against it. The CMake version is 0.1.0 (`CMakeLists.txt:6-9`).

The model integrates, column by column and hour by hour: surface and soil energy and water (including snow and a litter layer), aqueous geochemistry, microbial transformation of organic matter in litter and soil layers, plant biogeochemistry (radiation, photosynthesis and stomata, phenology, allocation, roots and uptake, nodules, litterfall), gas and solute transport, management and disturbance (harvest and cutting, fire, tillage, fertiliser, irrigation, warming, erosion), and hourly conservation checks.

The commit documented here is the fork branch `fix/r2-plant-balance`: upstream `09eb674a` plus two fix commits, `9669b817` (the plant balance counts root layer `NK`) and `cb243228` (the default-off switch `conserve_root_clamp`). The wiki's previous pin, `2dea74d9`, is 323 commits earlier.

## Execution modes

### 1. Standalone (`drivers/ecosim/`)

`drivers/ecosim/ecosim.F90` is the production driver (`program main`, `:1`). It reads the runfile into a buffer and parses it (`:77`, `:80`), builds the mesh (`SetMesh`, `:98`), allocates and initialises (`InitModules`, `:100`), reads site and soil input (`readi`, `:103`), sets the run type and length (`:107-111`), builds history tapes (`:126`), loops over forcing periods, repeats and climate years calling `AdvanceModelOneYear` (`:140-167`, call at `:156`), and tears down (`DestructEcoSIM`, `:172`). `AdvanceModelOneYear` (`drivers/ecosim/EcoSIMAPI.F90:343-571`) runs the day and hour loops; each hour calls `PrepHourlyWeather` (`:518`) and then `Run_EcoSIM_one_step` (`:37-128`):

| step | line | call | guard |
|---|---|---|---|
| 1 | `:49` | `HOUR1` | |
| 2 | `:56` | `WATSUB` | |
| 3 | `:63` | `MicrobeModel` | `microbial_model` |
| 3b | `:66` | `MLDataDiag` | `lmicrobeMLdiag` |
| 4 | `:73` | `PlantModel` | `plant_model .and. .not. ldo_radiation_test` |
| 5 | `:82` | `soluteModel` | `soichem_model` |
| 6 | `:91` | `TranspNoSalt` | |
| 7 | `:100` | `TranspSalt` | `salt_model` |
| 8 | `:110` | `EROSION` | (internal `iErosionMode`) |
| 9 | `:117` | `REDIST` | |
| 10 | `:122`, `:124` | `DiagSoilGasPressure`, `EndCheckBalances` | |

Full detail, including what each step calls and which steps can abort the run: [../core/main_orchestration.md](../core/main_orchestration.md).

### 2. ATS-coupled (`f90src/ATSUtils/`, `drivers/ATSEcoSIM/`)

The Advanced Terrestrial Simulator path uses `ATSEcoSIMInitMod` (`Init_EcoSIM_Soil`, which calls `SetMeshATS`, `set_ecosim_solver(30,10,20,20)` and `startsim`, `f90src/ATSUtils/ATSEcoSIMInitMod.F90:66-67`, `:147`), `ATSEcoSIMAdvanceMod` (`RunEcoSIMSurfaceBalance`), the coupling module `ATSCPLMod`, Alquimia-derived containers (`BGC_containers.F90`, `c_f_interface_module.F90`), `SharedDataMod` and compiler-neutral wrappers (`ecosim_wrappers.F90`). On this path `NK_col` is set to the ATS layer count (`ATSEcoSIMAdvanceMod.F90:121`) and prescribed phenology can be driven from ATS (`:286`). `drivers/ATSEcoSIM/ATSEcoSIM_test.F90` is a test harness. Documented in the APIs section.

### 3. Box and component drivers

| driver | program | purpose |
|---|---|---|
| `drivers/aquachem/` | `aquachem.F90` | stand-alone aqueous chemistry (`AquachemMod`, `AquaSaltChemMod`) |
| `drivers/boxsbgc/` | `batchsbgc.F90` | single-layer soil BGC box model (`batchmod`, `ChemMod`, `ForcTypeMod`, `MicIDMod`); can be fed forcing written by the standalone driver through `/bbgcforc/` |
| `drivers/mockbatch/` | `mockdriver.F90` | minimal mock driver (`MockMod`) |
| `drivers/plantbgc/` | `plantdriver.F90` | plant BGC harness; its module is now `PlantTestMod` (renamed from a second `PlantMod` since `2dea74d9`, which removes the old clash with `f90src/APIs/PlantMod.F90`) |
| `drivers/boxshared/` | | `ChemIDMod`, shared chemistry ids |

### 4. Test tools (`drivers/tools/`)

Twelve small programs exercising single readers and utilities: `ClimReader`, `ClimTransformer`, `EcoATSTest`, `EcoATSTest_old`, `GridReader`, `HFileTest`, `NamelistTest`, `PlantManagementReader`, `SoilManagementReader`, `SoilWarmReadTest`, `etimerTest`, `restartTest`.

## Subsystem map

| folder | role | wiki section |
|---|---|---|
| `f90src/Main/`, `f90src/Ecosim_mods/`, `f90src/Mesh/`, `f90src/Modelconfig/`, `f90src/Modelpars/`, `f90src/Utils/`, `f90src/Minimath/`, `f90src/DebugTools/` | setup, configuration, parameters, mesh, utilities | [core](../core/index.md) |
| `f90src/Ecosim_datatype/` (33 files) | allocatable global state | data types |
| `f90src/APIData/` (14 files) | the plant model's private state types (`plt_site`, `plt_morph`, `plt_biom`, ...), split into one module per group since `2dea74d9` | APIs |
| `f90src/APIs/` (13 files) | `PlantMod`, `MicBGCAPI`, `GeochemAPI`, `PlantAPI`, `PlantAPI4Uptake`, `PlantCanAPI`, six `Plant*TransferMod` copy modules, `SurfPhysAPI` stub | APIs |
| `f90src/Plant_bgc/` (25 files) | plant biogeochemistry | plant_bgc |
| `f90src/Microbial_bgc/` (`Box_Micmodel/` 15, `Layers_Micmodel/` 3) | soil microbial dynamics; eight catabolism modules split out since `2dea74d9` | microbial_bgc |
| `f90src/Geochem/` (`Box_chem/` 5, `Layers_chem/` 1) | equilibrium chemistry | geochem |
| `f90src/HydroTherm/` (15 files in 5 subfolders) | canopy, snow, soil and surface water and energy | hydrotherm |
| `f90src/Transport/` (`Nonsalt/` 5, `Salt/` 3) | gas and solute transport | transport |
| `f90src/Balances/` (7), `f90src/Disturbances/` (6) | state update, relayering, tillage; fertiliser, fire, warming, erosion | [balances_and_disturbances](../balances_and_disturbances/index.md) |
| `f90src/IOutils/` (12 + `HistData/` 11) | readers, restart, history (now split into submodules) | io_and_forcing |
| `f90src/Modelforc/` (5) | `hour1`, `day`, `PrepHourlyWeather`, annual accumulators, bio-aerosol deposition (new `DepositionMod`) | io_and_forcing |
| `f90src/ModelDiags/` (5) | balance audit, water table, soil gas pressure, ML diagnostics, organic-matter sums | [diagnostics](../diagnostics/index.md) |
| `f90src/Prescribed_pheno/` (1) | prescribed phenology (`ldo_sp_mode`) | plant_bgc |
| `f90src/ATSUtils/` (8) | ATS coupling | APIs |

The per-file list is [../reference/module_inventory.md](../reference/module_inventory.md); counts and changes since `2dea74d9` are in [source_tree.md](source_tree.md).

## Build

`build_EcoSIM.sh` configures CMake, builds the third-party libraries and then EcoSIM (`README.md:24-34`); the executable is `./build/bin/ecosim.f90.x` (`README.md:36`). The top-level `CMakeLists.txt` requires CMake 3.12 for Fortran submodule dependency scanning (`:2-3`; the history code now uses submodules), handles the ATS build flag (`:173-180`), adds `3rd-partylibs/` when not building for ATS (`:235`), and descends into `f90src/` and `drivers/` (`:274-275`). Third-party libraries are git submodules (hdf5, netcdf-c, netcdf-fortran, zlib, curl, c-blosc; `.gitmodules`).

## Behaviour a new user should know first

- STARTS, STARTQ and STARTE initialise once, in the start year (`EcoSIMAPI.F90:410`, `:434`, `:441`).
- The runfile must fit in 4096 bytes and must contain the `&bbgcforc` and `&Microbes` groups ([../core/model_config.md](../core/model_config.md) §1).
- An abort ends with `ENDRUN:` and exit status 0 ([../core/utilities.md](../core/utilities.md) §2).
- Four hourly checks can abort: WATSUB water, plant C/N/P, transport gas mass, end-of-hour soil water and gas tracers; energy is not checked ([../balances_and_disturbances/mass_balance.md](../balances_and_disturbances/mass_balance.md)).
- The calendar is real Gregorian (366-day leap years).

## Calibration parameters

None owned by this page.
