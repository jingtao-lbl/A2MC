---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** repository layout and `.F90` file counts at `cb243228`, compared with `2dea74d9`
**Last verified:** 2026-10-15
---

# Source tree

Counts are `.F90` files from `git ls-tree -r --name-only cb243228` (and `2dea74d9` for comparison). Headers, C files, CMake files, notebooks and data are not counted.

## 1. Repository root

| entry | what it is |
|---|---|
| `f90src/` | the model library: 226 `.F90` files (182 at `2dea74d9`) in 23 top-level subdirectories |
| `drivers/` | executables and test programs: 28 `.F90` files (28 at `2dea74d9`) in 8 subdirectories |
| `CMakeLists.txt` | top-level build (version 0.1.0, `:6-9`; CMake 3.12 minimum for Fortran submodules, `:2-3`) |
| `build_EcoSIM.sh`, `run_docker.sh`, `docker/` | build script, container helpers |
| `README.md`, `LICENSE.txt`, `Legal.txt` | documentation and licence (the last two are new) |
| `3rd-partylibs/` | submodules hdf5, netcdf-c, netcdf-fortran, zlib, curl, c-blosc (`.gitmodules`) |
| `cmake/` | `Modules/`, `Templates/`, and a new `build_timer.py` |
| `input_data/` | shipped parameter and forcing files, including `ecosim_pftpar_20260915.nc` (+ `.cdl`), `MicrobePars.20260211.nc` and three older `MicrobePars` versions, `plm_pftpar_20240924.nc`, `sorghum_pftpar_20241206.nc`, GHG series (`fatm_hist_GHGs_1750-2025.nc` and others) |
| `examples/` | `inputs/` and `run_dir/` with 16 example cases (`DaLake`, `Fen`, `FireCA`, `Pond`, `RiceUSTWT`, `SatePhenol`, `bare_soil`, `biocrust`, `biocrust_hillslope`, `blodgett`, `climeConst`, `dryland`, `jupyter_notebook`, `lake`, `macpore_test`, `radiation_test`) |
| `tests/` | namelist fixtures and management files (`example_nl`, `histtest_nl`, `pft_mgmnt_nl`, `timer_nl`, `pft_mgmt_Blodgett_v0_ex10.nc`, `..._ex12.nc`) and three new Python tests for the build timer, the management reader and runtime timings |
| `regression-tests/` | Python regression harness (`rtest_ecosim.py`, `mtest`, `Makefile`, `tests/`) |
| `nc_config/` | NetCDF template configuration |
| `calibration_tool/`, `ecosim_knowledge/` | new: a Python calibration helper (`run.py`, `env.py`, `agent/`, `cases/`) and HTML knowledge notes on individual processes |
| `ecosim-agent` | new git submodule (`bioepic-data/ecosim-agent`) |
| `.agents/`, `.claude/`, `.codex/`, `AGENTS.md`, `CLAUDE.md` | new agent configuration |
| `python_tools` | a submodule at `2dea74d9`; not part of the tree at `cb243228` (a local untracked copy may exist in a checkout) |

## 2. `f90src/` by subdirectory

| subdirectory | cb243228 | 2dea74d9 | change |
|---|---|---|---|
| `APIData/` | 14 | 1 | `PlantAPIData.F90` now only aggregates; 13 new `Plant*APIData.F90` type modules (site, morphology, biomass, allometry, BGC rates, root BGC, phenology, photosynthesis, radiation, energy-water, soil chemistry, disturbance, common) |
| `APIs/` | 13 | 7 | 6 new `Plant*TransferMod.F90` modules (`Canopy`, `Column`, `RootAxis`, `Root`, `State`, `Traits`) hold the copy code formerly inside `PlantAPI.F90` |
| `ATSUtils/` | 8 | 8 | |
| `Balances/` | 7 | 7 | |
| `DebugTools/` | 1 | 1 | |
| `Disturbances/` | 6 | 6 | |
| `Ecosim_datatype/` | 33 | 32 | `MLDataDiagType.F90` new |
| `Ecosim_mods/` | 4 | 4 | |
| `Geochem/Box_chem/`, `Layers_chem/` | 5, 1 | 5, 1 | |
| `HydroTherm/` (5 subfolders) | 15 | 15 | |
| `IOutils/` | 12 | 12 | |
| `IOutils/HistData/` | 11 | 0 | new: `HistDataType` implementation split into submodules (`HistAllocate*`, `HistRegister*`, `HistUpdate*`) |
| `Main/` | 2 | 2 | |
| `Mesh/` | 2 | 2 | |
| `Microbial_bgc/Box_Micmodel/` | 15 | 7 | 8 new catabolism modules: `AerobicBacteriaMod`, `CyanoBacteriaMod`, `DenitrifierMod`, `FermenterMod`, `FungiMod`, `MethanogenMod`, `MethanotrophMod`, `NitrifierMod` |
| `Microbial_bgc/Layers_Micmodel/` | 3 | 2 | `SoilPARAttenuationMod` new (soil PAR attenuation for cyanobacteria) |
| `Minimath/` | 3 | 3 | |
| `ModelDiags/` | 5 | 3 | `MLDataDiagMod`, `MicrobialDiagMod` new |
| `Modelconfig/` | 5 | 5 | |
| `Modelforc/` | 5 | 4 | `DepositionMod` new (bio-aerosol deposition) |
| `Modelpars/` | 8 | 8 | |
| `Plant_bgc/` | 25 | 24 | `RadiationDataMod` new |
| `Prescribed_pheno/` | 1 | 1 | |
| `Transport/Nonsalt/`, `Salt/` | 5, 3 | 5, 3 | |
| `Utils/` | 14 | 14 | `StrToolsMod.F90` renamed `StringToolsMod.F90` (module renamed too); `readme.md` new |
| **total** | **226** | **182** | |

## 3. `drivers/` by subdirectory

| subdirectory | files | contents |
|---|---|---|
| `drivers/ecosim/` | 2 | `ecosim.F90` (`program main`), `EcoSIMAPI.F90` (`readnamelist`, `AdvanceModelOneYear`, `Run_EcoSIM_one_step`, `regressiontest`, `write_modelconfig`) |
| `drivers/ATSEcoSIM/` | 1 | `ATSEcoSIM_test.F90` |
| `drivers/aquachem/` | 3 | `aquachem.F90`, `AquachemMod.F90`, `AquaSaltChemMod.F90` |
| `drivers/boxsbgc/` | 5 | `batchsbgc.F90`, `batchmod.F90`, `ChemMod.F90`, `ForcTypeMod.F90`, `MicIDMod.F90` |
| `drivers/boxshared/` | 1 | `ChemIDMod.F90` |
| `drivers/mockbatch/` | 2 | `mockdriver.F90`, `MockMod.F90` |
| `drivers/plantbgc/` | 2 | `plantdriver.F90`, `PlantTestMod.F90` (renamed from `PlantMod.F90`) |
| `drivers/tools/` | 12 | single-purpose test programs |

## 4. Differences since `2dea74d9` in one place

- 46 paths exist only at `cb243228` and 2 only at `2dea74d9`; the 2 are the renames `f90src/Utils/StrToolsMod.F90` → `StringToolsMod.F90` and `drivers/plantbgc/PlantMod.F90` → `PlantTestMod.F90`, so 44 files are new and none was deleted.
- Most new files are splits of large modules (plant API data and transfers, history, microbial catabolism) rather than new science. The genuinely new process code is bio-aerosol deposition (`DepositionMod`), soil PAR attenuation for cyanobacteria (`SoilPARAttenuationMod`, `CyanoBacteriaMod`), the radiation data type, and the ML diagnostics.
- Not visible in file counts: `git diff --shortstat 2dea74d9 cb243228 -- '*.F90'` reports 235 files changed, +28,387/-18,222 lines (new files included). Example: `f90src/Plant_bgc/RootMod.F90` grew from 3,853 to 6,260 lines.

## 5. Conventions worth knowing when navigating

- Module names match file names except: `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90` (module `MicBGCMod`), `MicAutoCplxFGMod.F90` (module `MicAutoCPLXMod`), `f90src/ATSUtils/BGC_containers.F90` (module `BGCContainers_module`), `f90src/Main/EcoSIMDesctruct.F90` (module `EcoSIMDesctruct`, the misspelling is in both), and the test programs `drivers/ATSEcoSIM/ATSEcoSIM_test.F90` and `drivers/tools/EcoATSTest_old.F90` (both `program EcoATSTest`). Several differ only in case (`minimathmod`, `readiMod`, `grosubsMod`, `stomatesMod`, `InitSOMBGCMOD`, `SoilHeatDatatype`, `EcosimConst`, `ecosim_Time_Mod`); Fortran is case-insensitive, so `git grep -i` is the safe search.
- `f90src/APIs/SurfPhysAPI.F90` and `f90src/HydroTherm/SurfPhys/SurfPhysAPI.F90` both exist (13 lines each); `f90src/ATSUtils/ecosim_wrappers.F90` has no module.
- `f90src/IOutils/HistData/*.F90` are `submodule (HistDataType)` units, not modules.
- `f90src/Utils/clock.o` is a committed object file.

## Calibration parameters

None owned by this page.
