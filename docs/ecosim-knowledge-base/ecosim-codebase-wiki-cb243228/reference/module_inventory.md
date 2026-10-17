---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** every `.F90` file under `f90src/` and `drivers/` at `cb243228`
**Last verified:** 2026-10-15
---

# Module inventory

One row per `.F90` file at `cb243228`: 254 files (226 under `f90src/`, 28 under `drivers/`), generated from `git ls-tree -r --name-only cb243228`. "Module" is the first `module`, `submodule` or `program` statement (blank when the file has none). "Since 2dea74d9": **new** (path absent at `2dea74d9`), **renamed** (path and module renamed), **modified** (content changed, `git diff --diff-filter=M`), or blank (identical). Counts: 44 new, 2 renamed, 189 modified, 19 unchanged. Removed since `2dea74d9`: none (the two paths that disappeared, `f90src/Utils/StrToolsMod.F90` and `drivers/plantbgc/PlantMod.F90`, are the renames). Lines are the file length at `cb243228`.


## `drivers/ATSEcoSIM/` (1)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `ATSEcoSIM_test.F90` | `EcoATSTest` | 181 |  | ATS coupling test harness exercising `BGCState`/`BGCProperties`/`BGCSizes` |

## `drivers/aquachem/` (3)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `AquaSaltChemMod.F90` | `AquaSaltChemMod` | 1003 |  | salt-mode aqueous chemistry box model (`RunModel_salt`, `initmodel_salt`) |
| `AquachemMod.F90` | `AquachemMod` | 443 |  | no-salt aqueous chemistry box model (`initmodel`, `getvarlist`) |
| `aquachem.F90` | `main` | 173 |  | stand-alone aqueous chemistry driver program |

## `drivers/boxsbgc/` (5)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `ChemMod.F90` | `ChemMod` | 272 |  | chemistry step for the box soil-BGC driver (`RunModel_nosalt`) |
| `ForcTypeMod.F90` | `ForcTypeMod` | 503 | modified | forcing type and reader for the box soil-BGC driver (`ReadFORC`, `UpdateFORC`) |
| `MicIDMod.F90` | `MicIDMod` | 109 |  | microbial variable ids for the box driver |
| `batchmod.F90` | `batchmod` | 1764 | modified | box soil-BGC model configuration and state update (`BatchModelConfig`, `Initboxbgc`) |
| `batchsbgc.F90` | `main` | 240 |  | single-layer soil-BGC driver program |

## `drivers/boxshared/` (1)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `ChemIDMod.F90` | `ChemIDMod` | 392 |  | shared chemistry variable ids (`getvarlist_nosalt`) |

## `drivers/ecosim/` (2)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `EcoSIMAPI.F90` | `EcoSIMAPI` | 668 | modified | standalone run control: `readnamelist`, `AdvanceModelOneYear`, `Run_EcoSIM_one_step`, `regressiontest`, `write_modelconfig` |
| `ecosim.F90` | `main` | 175 | modified | standalone driver `program main`: mesh, init, forcing-period and year loops, teardown |

## `drivers/mockbatch/` (2)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `MockMod.F90` | `MockMod` | 95 |  | mock model with five flux and five mass variables |
| `mockdriver.F90` | `main` | 166 |  | mock driver program |

## `drivers/plantbgc/` (2)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `PlantTestMod.F90` | `PlantTestMod` | 95 | renamed from `PlantMod.F90` | plant BGC harness module (`runplant`, `initmodel`) |
| `plantdriver.F90` | `main` | 165 | modified | plant BGC harness program |

## `drivers/tools/` (12)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `ClimReader.F90` | `ClimReader` | 32 |  | test: read climate forcing |
| `ClimTransformer.F90` | `ClimTransformer` | 274 |  | tool: reshape climate arrays |
| `EcoATSTest.F90` | `EcoATSTest` | 34 |  | test: ATS and EcoSIM size initialisation |
| `EcoATSTest_old.F90` | `EcoATSTest` | 65 |  | older ATS coupling test |
| `GridReader.F90` | `GridReader` | 51 |  | test: read the grid file |
| `HFileTest.F90` | `HFileTest` | 122 | modified | test: history file writing |
| `NamelistTest.F90` | `NamelistTest` | 134 |  | test: namelist parsing |
| `PlantManagementReader.F90` | `PlantManagementReader` | 81 |  | test: plant management reader |
| `SoilManagementReader.F90` | `SoilManagementReader` | 30 |  | test: soil management reader |
| `SoilWarmReadTest.F90` | `SoilWarmReadTest` | 26 |  | test: soil-warming reference reader |
| `etimerTest.F90` | `etimerTest` | 47 | modified | test: simulation clock |
| `restartTest.F90` | `restartTest` | 76 | modified | test: restart I/O |

## `f90src/APIData/` (14)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `PlantAPICommonData.F90` | `PlantAPICommonData` | 29 | new | common pieces of the plant API data (split from `PlantAPIData`) |
| `PlantAPIData.F90` | `PlantAPIData` | 104 | modified | aggregates the plant API data types; `InitPlantAPIData`, `DestructPlantAPIData` |
| `PlantAllometryAPIData.F90` | `PlantAllometryAPIData` | 162 | new | plant allometry state `plt_allom` |
| `PlantBGCRatesAPIData.F90` | `PlantBGCRatesAPIData` | 172 | new | plant BGC rates `plt_bgcr` |
| `PlantBiomassAPIData.F90` | `PlantBiomassAPIData` | 304 | new | plant biomass state `plt_biom` |
| `PlantDisturbanceAPIData.F90` | `PlantDisturbanceAPIData` | 117 | new | plant disturbance state `plt_distb` (harvest type, `THIN_pft`, `FracBiomHarvsted`) |
| `PlantEnergyWaterAPIData.F90` | `PlantEnergyWaterAPIData` | 157 | new | plant energy and water state `plt_ew` |
| `PlantMorphologyAPIData.F90` | `PlantMorphologyAPIData` | 395 | new | plant morphology state `plt_morph` (incl. `MaxSoilLays4Root_pft`) |
| `PlantPhenologyAPIData.F90` | `PlantPhenologyAPIData` | 197 | new | plant phenology state `plt_pheno` |
| `PlantPhotosynthesisAPIData.F90` | `PlantPhotosynthesisAPIData` | 172 | new | photosynthesis state `plt_photo` |
| `PlantRadiationAPIData.F90` | `PlantRadiationAPIData` | 104 | new | plant radiation state `plt_rad` |
| `PlantRootBGCAPIData.F90` | `PlantRootBGCAPIData` | 298 | new | root BGC state `plt_rbgc` |
| `PlantSiteAPIData.F90` | `PlantSiteAPIData` | 114 | new | site state seen by the plant model `plt_site` (`NU`, `NK`, `MaxNumRootLays`, `NL`) |
| `PlantSoilChemistryAPIData.F90` | `PlantSoilChemistryAPIData` | 140 | new | soil chemistry seen by the plant model `plt_soilchem` |

## `f90src/APIs/` (13)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `GeochemAPI.F90` | `GeochemAPI` | 371 | modified | equilibrium-chemistry API (`soluteModel`) |
| `MicBGCAPI.F90` | `MicBGCAPI` | 696 | modified | microbial API: `MicrobeModel` per-layer loop, soil fire hook, send/receive |
| `PlantAPI.F90` | `PlantAPI` | 104 | modified | plant API entry points `PlantAPISend`, `PlantAPIRecv` |
| `PlantAPI4Uptake.F90` | `PlantAPI4Uptake` | 285 | modified | plant API for prescribed phenology (`PlantUptakeAPISend/Recv`) |
| `PlantCanAPI.F90` | `PlantCanAPI` | 271 | modified | canopy radiation API (`PlantAPICanMSend/Recv`) |
| `PlantCanopyTransferMod.F90` | `PlantCanopyTransferMod` | 375 | new | ordered canopy copies used by `PlantAPISend/Recv` |
| `PlantColumnTransferMod.F90` | `PlantColumnTransferMod` | 395 | new | ordered column copies (sets `plt_site%NU = NUM_col`, `NK`, `MaxNumRootLays`) |
| `PlantMod.F90` | `PlantMod` | 142 | modified | hourly `PlantModel` (balance bracket, phenology, uptake, growth) and `PlantCanopyRadsModel` |
| `PlantRootAxisTransferMod.F90` | `PlantRootAxisTransferMod` | 193 | new | ordered root-axis copies |
| `PlantRootTransferMod.F90` | `PlantRootTransferMod` | 259 | new | ordered root copies |
| `PlantStateTransferMod.F90` | `PlantStateTransferMod` | 450 | new | ordered plant state copies |
| `PlantTraitsTransferMod.F90` | `PlantTraitsTransferMod` | 205 | new | ordered trait copies (`SendPlantTraits`) |
| `SurfPhysAPI.F90` | `SurfPhysAPI` | 13 | modified | empty stub (13 lines) |

## `f90src/ATSUtils/` (8)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `ATSCPLMod.F90` | `ATSCPLMod` | 375 | modified | ATS coupling state exchange (`ATS2EcoSIMData`, `EcoSIM2ATSData`) |
| `ATSEcoSIMAdvanceMod.F90` | `ATSEcoSIMAdvanceMod` | 382 | modified | ATS-path hourly advance (`RunEcoSIMSurfaceBalance`) |
| `ATSEcoSIMInitMod.F90` | `ATSEcoSIMInitMod` | 158 | modified | ATS-path initialisation (`Init_EcoSIM_Soil`) |
| `ATSUtilsMod.F90` | `ATSUtilsMod` | 47 | modified | ATS date conversion (`ComputeDatefromATS`) |
| `BGC_containers.F90` | `BGCContainers_module` | 225 | modified | Alquimia-derived containers `BGCState`, `BGCProperties`, `BGCSizes` |
| `SharedDataMod.F90` | `SharedDataMod` | 209 | modified | ATS scratch data and grid sizes (sets `JZ`) |
| `c_f_interface_module.F90` | `c_f_interface_module` | 187 | modified | C/Fortran string interop (Alquimia-derived) |
| `ecosim_wrappers.F90` |  | 126 | modified | compiler-neutral wrappers `EcoSIM_Setup`, `EcoSIM_Advance`, `EcoSIM_Shutdown` (no module) |

## `f90src/Balances/` (7)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `ErosionBalMod.F90` | `ErosionBalMod` | 238 | modified | sediment sinking from ponds (`SinkSediments`) |
| `LateralTranspMod.F90` | `LateralTranspMod` | 435 | modified | sums directional fluxes into net cell changes (`XGridTranspt`) |
| `RedistDataMod.F90` | `RedistDataMod` | 179 | modified | shared transport/redistribution arrays |
| `RedistMod.F90` | `RedistMod` | 1511 | modified | end-of-hour state update `redist`; NEE/NBP/HR accumulators; tillage call |
| `RunoffBalMod.F90` | `RunoffBalMod` | 696 | modified | boundary solute losses (call commented out in `redist`) |
| `SoilLayerDynMod.F90` | `SoilLayerDynMod` | 2078 | modified | soil relayering (`UpdateSoilGrids`), moves `NU`/`NL` |
| `TillageMixMod.F90` | `TillageMixMod` | 621 | modified | tillage mixing at solar noon (`ApplyTillageMixing`) |

## `f90src/DebugTools/` (1)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `DebugToolMod.F90` | `DebugToolMod` | 102 | modified | `PrintInfo`, `DebugPrint`, `do_debug`, `GetSoilWaterMass` (all gated by `lverb`) |

## `f90src/Disturbances/` (6)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `EcosysWarmingMod.F90` | `EcosysWarmingMod` | 638 | modified | warming experiments: cable, IR, open-top chamber |
| `ErosionMod.F90` | `ErosionMod` | 987 | modified | sediment detachment and transport (`erosion`) |
| `FertilizerMod.F90` | `FertilizerMod` | 780 | modified | mineral fertiliser, residue/manure, inhibitors at solar noon |
| `FireMod.F90` | `FireMod` | 117 | modified | fire-year schedule (`config_fire`, `check_fire`) |
| `PlantDisturbMod.F90` | `PlantDisturbMod` | 77 | modified | landscape grazing staging (`PrepLandscapeGrazing`) |
| `SoilDisturbMod.F90` | `SoilDisturbMod` | 395 | modified | soil fire and litter removal (`SOMRemovalByDisturbance`) |

## `f90src/Ecosim_datatype/` (33)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `AqueChemDatatype.F90` | `AqueChemDatatype` | 231 | modified | aqueous chemistry state |
| `BalanceCheckDataType.F90` | `BalanceCheckDataType` | 39 | modified | balance-check begin/end storages |
| `CanopyDataType.F90` | `CanopyDataType` | 619 | modified | canopy state |
| `CanopyRadDataType.F90` | `CanopyRadDataType` | 92 | modified | canopy radiation state |
| `ChemTranspDataType.F90` | `ChemTranspDataType` | 114 | modified | chemical transport state |
| `ClimForcDataType.F90` | `ClimForcDataType` | 369 | modified | climate forcing state |
| `EcoSIMCtrlDataType.F90` | `EcoSIMCtrlDataType` | 66 | modified | run-control state (`NPX`, `NPY`, ...) |
| `EcoSIMHistMod.F90` | `EcoSIMHistMod` | 60 | modified | history-related globals (`PREFIX`, ...) |
| `EcoSimSumDataType.F90` | `EcoSimSumDataType` | 68 | modified | landscape sums |
| `EcosimBGCFluxType.F90` | `EcosimBGCFluxType` | 100 | modified | ecosystem BGC fluxes (`Canopy_NEE_col`, ...) |
| `FertilizerDataType.F90` | `FertilizerDataType` | 75 | modified | fertiliser state |
| `FlagDataType.F90` | `FlagDataType` | 77 | modified | flags |
| `GridDataType.F90` | `GridDataType` | 94 | modified | grid geometry and layer indices (`NU_col`, `NK_col`, `MaxNumRootLays_col`, `NL_col`) |
| `IrrigationDataType.F90` | `IrrigationDataType` | 242 | modified | irrigation state |
| `LandSurfDataType.F90` | `LandSurfDataType` | 86 | modified | land-surface state |
| `MLDataDiagType.F90` | `MLDataDiagType` | 153 | new | state for the ML diagnostics |
| `MicrobialDataType.F90` | `MicrobialDataType` | 205 | modified | microbial state |
| `NumericalAuxMod.F90` | `NumericalAuxMod` | 42 | modified | numerical work arrays |
| `PlantDataRateType.F90` | `PlantDataRateType` | 440 | modified | plant rate state |
| `PlantMgmtDataType.F90` | `PlantMgmtDataType` | 112 | modified | plant management state (`NP_col`, day-indexed harvest arrays) |
| `PlantTraitDataType.F90` | `PlantTraitDataType` | 615 | modified | plant traits per PFT |
| `PlantTraitTableMod.F90` | `PlantTraitTableMod` | 418 | modified | plant trait table `*_tab` arrays |
| `RootDataType.F90` | `RootDataType` | 468 | modified | root state (`irootType_col`, `MaxSoilLays4Root_pft`) |
| `SOMDataType.F90` | `SOMDataType` | 150 | modified | soil organic matter state |
| `SedimentDataType.F90` | `SedimentDataType` | 122 | modified | sediment state |
| `SnowDataType.F90` | `SnowDataType` | 258 | modified | snow state |
| `SoilBGCDataType.F90` | `SoilBGCDataType` | 427 | modified | soil BGC state |
| `SoilHeatDataType.F90` | `SoilHeatDatatype` | 91 | modified | soil heat state |
| `SoilPhysDataType.F90` | `SoilPhysDataType` | 117 | modified | soil physics state |
| `SoilPropertyDataType.F90` | `SoilPropertyDataType` | 121 | modified | soil properties |
| `SoilWaterDataType.F90` | `SoilWaterDataType` | 355 | modified | soil water state |
| `SurfLitterDataType.F90` | `SurfLitterDataType` | 105 | modified | surface litter state (`XTillCorp_col`) |
| `SurfSoilDataType.F90` | `SurfSoilDataType` | 84 | modified | surface soil state |

## `f90src/Ecosim_mods/` (4)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `InitAllocMod.F90` | `InitAllocMod` | 193 | modified | single allocation entry `InitAlloc`; `InitPlantMorphSize` |
| `StarteMod.F90` | `StarteMod` | 576 | modified | start-year chemistry initialisation `starte` |
| `StartqMod.F90` | `StartqMod` | 963 | modified | start-year plant initialisation `startq` (root axial resistance from ARSRA/RVSR) |
| `StartsMod.F90` | `StartsMod` | 1172 | modified | start-year soil initialisation `starts`; `set_ecosim_solver`; ATS `startsim`; `InitControlParms` |

## `f90src/Geochem/Box_chem/` (5)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `ChemEquilibriaMod.F90` | `ChemEquilibriaMod` | 835 | modified | no-salt equilibrium chemistry |
| `GeoChemMathMod.F90` | `GeoChemMathMod` | 62 | modified | quadratic reaction solvers |
| `InitSoluteMod.F90` | `InitSoluteMod` | 1745 | modified | solute model initialisation and solubility equilibria |
| `SaltChemEquilibriaMod.F90` | `SaltChemEquilibriaMod` | 2782 | modified | salt equilibrium chemistry |
| `SoluteChemDataType.F90` | `SoluteChemDataType` | 609 | modified | solute chemistry data type |

## `f90src/Geochem/Layers_chem/` (1)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `SoluteMod.F90` | `SoluteMod` | 1298 | modified | layered geochemistry: equilibria, fertiliser bands, urea hydrolysis |

## `f90src/HydroTherm/CanopyPhys/` (1)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `CanopyHydroMod.F90` | `CanopyHydroMod` | 103 | modified | canopy interception (`CanopyInterceptPrecip`) |

## `f90src/HydroTherm/PhysData/` (3)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `HydroThermData.F90` | `HydroThermData` | 190 | modified | hydrothermal state |
| `PhysPars.F90` | `PhysPars` | 49 | modified | physical parameters (minimum resistances, snow depth) |
| `SoilPhysParaMod.F90` | `SoilPhysParaMod` | 310 | modified | soil water potential, thermal conductivity, deep soil |

## `f90src/HydroTherm/SnowPhys/` (4)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `SnowBalanceMod.F90` | `SnowBalanceMod` | 848 | modified | snow mass update and negative-mass/high-temperature aborts |
| `SnowPhysData.F90` | `SnowPhysData` | 170 | modified | snow physics state |
| `SnowPhysMod.F90` | `SnowPhysMod` | 1930 | modified | snow model |
| `SnowTransportMod.F90` | `SnowTransportMod` | 294 | modified | water and tracer transport in snow |

## `f90src/HydroTherm/SoilPhys/` (3)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `SoilHydroParaMod.F90` | `SoilHydroParaMod` | 1045 | modified | soil hydraulic parameters and properties |
| `WatsubDataMod.F90` | `WatsubDataMod` | 136 | modified | WATSUB work arrays |
| `WatsubMod.F90` | `WatsubMod` | 2690 | modified | soil water and energy (`watsub`) with per-sub-cycle water check |

## `f90src/HydroTherm/SurfPhys/` (4)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `SurfLitterPhysMod.F90` | `SurfLitterPhysMod` | 886 | modified | surface litter energy and water |
| `SurfPhysAPI.F90` | `SurfPhysAPI` | 13 | modified | stub (13 lines) |
| `SurfPhysData.F90` | `SurfPhysData` | 134 | modified | surface physics state |
| `SurfPhysMod.F90` | `SurfPhysMod` | 1831 | modified | surface physics |

## `f90src/IOutils/` (12)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `ClimReadMod.F90` | `ClimReadMod` | 1119 | modified | climate and GHG forcing readers |
| `ForcWriterMod.F90` | `ForcWriterMod` | 286 | modified | writes forcing for the box soil-BGC driver |
| `HistDataType.F90` | `HistDataType` | 752 | modified | history state type and interfaces (implementations in `HistData/`) |
| `HistFileMod.F90` | `HistFileMod` | 2976 | modified | history tapes (`hist_nhtfrq`, `hist_mfilt`, `hist_fincl*`) |
| `MicrobeInfoMod.F90` | `MicrobeInfoMod` | 19 | modified | writes microbial traits |
| `PlantInfoMod.F90` | `PlantInfoMod` | 1909 | modified | plant trait and management readers (live `ReadPlantTraitTable`; harvest record parser) |
| `ReadManagementMod.F90` | `ReadManagementMod` | 686 | modified | soil management readers: tillage, irrigation, fertiliser, fire |
| `RestartMod.F90` | `RestartMod` | 10543 | modified | restart read and write |
| `bhistMod.F90` | `bhistMod` | 468 | modified | legacy history helpers |
| `readimod.F90` | `readiMod` | 1078 | modified | site and topography reader (`readi`, `readTopoNC`: `NUI`, `NJ`, `NK`, `NL`) |
| `readsmod.F90` | `readsmod` | 377 | modified | annual climate and soil forcing (`ReadClimSoilForcing`, fire-year trigger) |
| `restUtilMod.F90` | `restUtilMod` | 1935 | modified | restart variable helpers |

## `f90src/IOutils/HistData/` (11)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `HistAllocateColumn.F90` | `HistAllocateColumn` | 239 | new | submodule of `HistDataType`: column field allocation |
| `HistAllocatePlant.F90` | `HistAllocatePlant` | 198 | new | submodule: plant field allocation |
| `HistAllocateProfile.F90` | `HistAllocateProfile` | 277 | new | submodule: profile field allocation |
| `HistRegisterColumn.F90` | `HistRegisterColumn` | 973 | new | submodule: column field registration (names, units) |
| `HistRegisterPlant.F90` | `HistRegisterPlant` | 811 | new | submodule: plant field registration |
| `HistRegisterSoilBGC.F90` | `HistRegisterSoilBGC` | 635 | new | submodule: soil BGC field registration |
| `HistRegisterSoilPhysRoot.F90` | `HistRegisterSoilPhysRoot` | 469 | new | submodule: soil physics and root field registration |
| `HistUpdate.F90` | `HistUpdate` | 250 | new | submodule: `hist_update` driver |
| `HistUpdateColumn.F90` | `HistUpdateColumn` | 396 | new | submodule: column field update |
| `HistUpdatePlant.F90` | `HistUpdatePlant` | 470 | new | submodule: plant field update |
| `HistUpdateSoil.F90` | `HistUpdateSoil` | 264 | new | submodule: soil field update |

## `f90src/Main/` (2)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `EcoSIMDesctruct.F90` | `EcoSIMDesctruct` | 143 | modified | teardown `DestructEcoSIM` |
| `InitEcoSIM.F90` | `InitEcoSIM` | 62 | modified | setup `InitModules` |

## `f90src/Mesh/` (2)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `GridConsts.F90` | `GridConsts` | 57 | modified | grid constants and `bounds` |
| `GridMod.F90` | `GridMod` | 229 | modified | `SetMesh`, `SetMeshATS`, `get_col`, `get_pft` |

## `f90src/Microbial_bgc/Box_Micmodel/` (15)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `AerobicBacteriaMod.F90` | `AerobicBacteriaMod` | 217 | new | aerobic heterotrophic bacteria catabolism |
| `CyanoBacteriaMod.F90` | `CyanoBacteriaMod` | 264 | new | cyanobacteria catabolism and PAR response |
| `DenitrifierMod.F90` | `DenitrifierMod` | 370 | new | facultative denitrifier catabolism |
| `FermenterMod.F90` | `FermenterMod` | 165 | new | fermenter and acetogenic N2-fixer catabolism |
| `FungiMod.F90` | `FungiMod` | 174 | new | aerobic fungi catabolism |
| `MethanogenMod.F90` | `MethanogenMod` | 275 | new | acetoclastic and hydrogenotrophic methanogens |
| `MethanotrophMod.F90` | `MethanotrophMod` | 524 | new | aerobic and anaerobic methanotrophs |
| `MicAutoCplxFGMod.F90` | `MicAutoCPLXMod` | 1449 | modified | autotroph complex (module `MicAutoCPLXMod`) |
| `MicBGCFGMod.F90` | `MicBGCMod` | 3435 | modified | single-layer soil BGC `SoilBGCOneLayer` (module `MicBGCMod`) |
| `MicFluxTypeMod.F90` | `MicFluxTypeMod` | 493 | modified | microbial flux container |
| `MicForcTypeMod.F90` | `MicForcTypeMod` | 180 | modified | microbial forcing container |
| `MicStateTraitTypeMod.F90` | `MicStateTraitTypeMod` | 157 | modified | microbial state and trait container |
| `MicrobMathFuncMod.F90` | `MicrobMathFuncMod` | 594 | modified | microbial helper functions (uptake, reserve transfers, temperature) |
| `MicrobeDiagTypes.F90` | `MicrobeDiagTypes` | 1004 | modified | microbial diagnostic containers |
| `NitrifierMod.F90` | `NitrifierMod` | 563 | new | ammonia and nitrite oxidisers |

## `f90src/Microbial_bgc/Layers_Micmodel/` (3)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `InitSOMBGCMod.F90` | `InitSOMBGCMOD` | 873 | modified | SOM and microbial initialisation; sizes `micpar` (`InitSOMBGC`) |
| `SoilBGCNLayMod.F90` | `SoilBGCNLayMod` | 229 | modified | layered soil BGC helpers (`initNitro`, `DownwardMixOM`) |
| `SoilPARAttenuationMod.F90` | `SoilPARAttenuationMod` | 139 | new | soil PAR extinction coefficient (`CalcKSoilPAR`) |

## `f90src/Minimath/` (3)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `LinearAlgebraMod.F90` | `LinearAlgebraMod` | 126 | modified | sparse matrix-vector helpers |
| `MiniFuncMod.F90` | `MiniFuncMod` | 239 | modified | small physics functions (tortuosity, diffusivity, day length, equation of time) |
| `MiniMathMod.F90` | `minimathmod` | 727 | modified | safe arithmetic (`safe_adb`, `AZMAX1`, `isclose`, flux limiters) |

## `f90src/ModelDiags/` (5)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `BalancesMod.F90` | `BalancesMod` | 521 | modified | hourly water and gas-tracer closure (`BegCheckBalances`, `EndCheckBalances`) |
| `HydrologyDiagMod.F90` | `HydrologyDiagMod` | 122 | modified | water-table depth (`DiagWaterTBLDepz`) |
| `MLDataDiagMod.F90` | `MLDataDiagMod` | 269 | new | top-30-cm ML feature diagnostics (`MLDataDiag`) |
| `MicrobialDiagMod.F90` | `MicrobialDiagMod` | 530 | new | organic-matter and microbial sums (moved from `SoilBGCNLayMod`) |
| `SoilDiagsMod.F90` | `SoilDiagsMod` | 70 | modified | soil gas partial pressures (`DiagSoilGasPressure`) |

## `f90src/Modelconfig/` (5)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `EcoSIMConfig.F90` | `EcoSIMConfig` | 100 | modified | sizes, restart type, `transport_on`/`column_mode`/`do_instequil` |
| `EcoSIMCtrlMod.F90` | `EcoSIMCtrlMod` | 185 | modified | run-control switches incl. `guard_floor_dying_stand`, `conserve_root_clamp`; `frectyp`; `get_sim_len` |
| `EcoSIMSolverPar.F90` | `EcoSIMSolverPar` | 26 | modified | solver time steps and cycle counts; `oscal_test` |
| `ElmIDMod.F90` | `ElmIDMod` | 221 | modified | integer ids: elements, harvest, tillage, fertiliser, phenology |
| `TracerIDMod.F90` | `TracerIDMod` | 410 | modified | tracer ids (`InitTracerIDs`) |

## `f90src/Modelforc/` (5)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `DayMod.F90` | `DayMod` | 309 | modified | daily driver `day`: solar noon, tillage fraction, irrigation |
| `DepositionMod.F90` | `DepositionMod` | 100 | new | bio-aerosol deposition (`ApplyBioAerosol`) |
| `Hour1Mod.F90` | `Hour1Mod` | 1741 | modified | hourly setup `hour1`: balance snapshot, radiation, fertiliser |
| `WthrMod.F90` | `WthrMod` | 577 | modified | hourly weather `PrepHourlyWeather`; IR/OTC warming |
| `YearMod.F90` | `YearMod` | 142 | modified | annual accumulator reset `SetAnnualAccumlators` |

## `f90src/Modelpars/` (8)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `ChemTracerParsMod.F90` | `ChemTracerParsMod` | 56 | modified | diffusivities and gas solubilities |
| `EcoSiMParDataMod.F90` | `EcoSiMParDataMod` | 9 | modified | global `pltpar`, `micpar` |
| `MicBGCPars.F90` | `MicBGCPars` | 568 | modified | microbial parameter type `MicParType` |
| `MicrobeConfigMod.F90` | `MicrobeConfigMod` | 48 | modified | `/Microbes/` namelist reader |
| `NitroPars.F90` | `NitroPars` | 371 | modified | microbial kinetic constants; `ReadPars` from `micpar_file_in`; `EFIRE` |
| `PlantBGCPars.F90` | `PlantBGCPars` | 322 | modified | plant constants (`Rax_ref`), `plant_bgc_par_type`, `InitVegPars` |
| `SoluteParMod.F90` | `SoluteParMod` | 155 | modified | equilibrium constants |
| `TracerPropMod.F90` | `TracerPropMod` | 149 | modified | gas solubility and molecular weight functions |

## `f90src/Plant_bgc/` (25)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `ExtractsMod.F90` | `ExtractsMod` | 430 | modified | aggregates plant-soil exchanges (`extracts`) |
| `GrosubsMod.F90` | `grosubsMod` | 736 | modified | `GrowPlants`, `GrowOnePlant`, `Live2DeadTransformation` (module `grosubsMod`) |
| `InitPlantMod.F90` | `InitPlantMod` | 1314 | modified | plant initialisation at planting (`StartPlants`, `SeedDeposition`) |
| `InitVegBGC.F90` | `InitVegBGC` | 83 | modified | irradiance geometry (`InitIrradianceGeometry`) |
| `LitterFallMod.F90` | `LitterFallMod` | 1064 | modified | litterfall, dead plants, reseeding |
| `NoduleBGCMod.F90` | `NoduleBGCMod` | 880 | modified | canopy and root nodules |
| `NutUptakeMod.F90` | `NutUptakeMod` | 1578 | modified | root and mycorrhizal nutrient and O2 uptake |
| `PhotoSynsMod.F90` | `PhotoSynsMod` | 572 | modified | GPP for C3 and C4 (`ComputeGPP_C3`, `ComputeGPP_C4`) |
| `PlantBalMod.F90` | `PlantBalMod` | 949 | modified | plant C/N/P balance (`EnterPlantBalance`, `CheckPlantBalanceZ`, `SumRootPoolsForBalance`) |
| `PlantBranchMod.F90` | `PlantBranchMod` | 4188 | modified | branch growth, leaf nutrient withdrawal, branch phenology reset |
| `PlantDebugMod.F90` | `PlantDebugMod` | 110 | modified | plant debugging helpers |
| `PlantDisturbByFireMod.F90` | `PlantDisturbByFireMod` | 525 | modified | plant fire |
| `PlantDisturbByGrazingMod.F90` | `PlantDisturbByGrazingMod` | 473 | modified | grazing and herbivory removal |
| `PlantDisturbByTillageMod.F90` | `PlantDisturbByTillageMod` | 586 | modified | tillage damage to plants |
| `PlantDisturbsMod.F90` | `PlantDisturbsMod` | 2336 | modified | harvest, cutting, thinning, standing dead, disturbance litter |
| `PlantMathFuncMod.F90` | `PlantMathFuncMod` | 688 | modified | plant helper functions |
| `PlantNonstElmDynMod.F90` | `PlantNonstElmDynMod` | 1052 | modified | nonstructural element transfers incl. shoot-root |
| `PlantPhenolMod.F90` | `PlantPhenolMod` | 1533 | modified | phenology; planting via `StartPlants` |
| `RadiationDataMod.F90` | `RadiationDataMod` | 84 | new | radiation data type (`InitRadiationData`) |
| `RootGasMod.F90` | `RootGasMod` | 828 | modified | root-soil gas exchange |
| `RootMod.F90` | `RootMod` | 6260 | modified | root growth, geometry, secondary growth, deficit charging |
| `StomatesMod.F90` | `stomatesMod` | 1071 | modified | stomata and C3/C4 canopy photosynthesis (module `stomatesMod`) |
| `SurfaceRadiationMod.F90` | `SurfaceRadiationMod` | 1925 | modified | canopy and surface radiation |
| `UptakePars.F90` | `UptakePars` | 60 | modified | uptake iteration parameters |
| `UptakesMod.F90` | `UptakesMod` | 1645 | modified | `RootUptakes`: canopy water, root hydraulics, nutrient uptake |

## `f90src/Prescribed_pheno/` (1)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `PrescribePhenolMod.F90` | `PrescribePhenolMod` | 366 | modified | prescribed phenology (LAI/SAI, Jackson root profile) |

## `f90src/Transport/Nonsalt/` (5)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `InitNoSaltTransportMod.F90` | `InitNoSaltTransportMod` | 615 | modified | transport initialisation per hour |
| `TranspNoSaltDataMod.F90` | `TranspNoSaltDataMod` | 468 | modified | transport work arrays |
| `TranspNoSaltFastMod.F90` | `TranspNoSaltFastMod` | 1058 | modified | fast gas sub-steps with mass checks |
| `TranspNoSaltMod.F90` | `TranspNoSaltMod` | 440 | modified | `TranspNoSalt` driver with `ExitMassCheck` |
| `TranspNoSaltSlowMod.F90` | `TranspNoSaltSlowMod` | 3622 | modified | slow solute/gas sub-steps with mass checks |

## `f90src/Transport/Salt/` (3)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `IngridTranspMod.F90` | `IngridTranspMod` | 1625 | modified | salt transport within the grid |
| `TranspSaltDataMod.F90` | `TranspSaltDataMod` | 98 | modified | salt transport arrays |
| `TranspSaltMod.F90` | `TranspSaltMod` | 419 | modified | `TranspSalt` driver |

## `f90src/Utils/` (14)

| file | module | lines | since 2dea74d9 | purpose |
|---|---|---|---|---|
| `EcoSimConst.F90` | `EcosimConst` | 60 | modified | physical constants and thresholds (module `EcosimConst`) |
| `ModelStatusType.F90` | `ModelStatusType` | 86 | modified | status/message object |
| `StringToolsMod.F90` | `StringToolsMod` | 439 | renamed from `StrToolsMod.F90` | string parsing (`parse_var_val_string`) |
| `TestMod.F90` | `TestMod` | 340 | modified | regression-test object |
| `UnitMod.F90` | `UnitMod` | 130 | modified | unit conversions (`units`) |
| `abortutils.F90` | `abortutils` | 627 | modified | `endrun` (plain `stop`), `destroy` |
| `data_const_mod.F90` | `data_const_mod` | 65 | modified | shared constants (`spval`) |
| `data_kind_mod.F90` | `data_kind_mod` | 26 | modified | real kind `r8` |
| `ecosim_log_mod.F90` | `ecosim_log_mod` | 78 | modified | log message helper |
| `ecosim_time_mod.F90` | `ecosim_Time_Mod` | 1094 | modified | simulation clock `ecosim_time_type` (module `ecosim_Time_Mod`) |
| `fileUtil.F90` | `fileUtil` | 522 | modified | files and the 4096-byte namelist buffer |
| `ncdio_pio.F90` | `ncdio_pio` | 3295 | modified | NetCDF wrapper |
| `shr_infnan_mod.F90` | `shr_infnan_mod` | 1843 | modified | NaN/Inf tests (generated) |
| `timings.F90` | `timings` | 207 | modified | wall-clock profiling (`do_timing`) |

## Notes

- New files are mostly splits of large modules: 13 plant API data types out of `f90src/APIData/PlantAPIData.F90`, 6 transfer modules out of `f90src/APIs/PlantAPI.F90`, 11 history submodules of `f90src/IOutils/HistDataType.F90`, 8 microbial catabolism modules out of `MicBGCFGMod.F90` and `MicAutoCplxFGMod.F90`, and the organic-matter sums moved into `f90src/ModelDiags/MicrobialDiagMod.F90`. New process code: `DepositionMod` (bio-aerosol), `SoilPARAttenuationMod` and `CyanoBacteriaMod` (cyanobacteria and soil PAR), `RadiationDataMod`, and the ML diagnostics (`MLDataDiagMod`, `MLDataDiagType`).
- Fortran is case-insensitive; several module names differ from the file name only in case. Search with `git grep -i`.
- The `.F90` count excludes the C helpers in `f90src/Utils/` (`clock.c`, `getfilename.c`, `dtypes.h`) and the committed object `clock.o`.
- Directory-level counts and the repository layout: [../overview/source_tree.md](../overview/source_tree.md).

## Calibration parameters

None owned by this page.
