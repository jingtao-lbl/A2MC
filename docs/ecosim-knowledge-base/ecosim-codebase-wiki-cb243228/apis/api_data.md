---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/APIData/` (14 files), lifecycle callers in `f90src/Ecosim_mods/InitAllocMod.F90` and `f90src/Main/EcoSIMDesctruct.F90`
**Last verified:** 2026-10-15
---

# API Data Layer: `f90src/APIData/`

## What it is

`f90src/APIData/` defines the containers the plant kernels in `f90src/Plant_bgc/` work on. Each container is a derived type with pointer components sized for one column (`JP1` PFT slots, `JZ1` layers, branches, nodes, root types), and each has one module-level singleton declared `public, target`. `PlantAPISend` fills them from the grid arrays of `f90src/Ecosim_datatype/` at the start of every column's plant step and `PlantAPIRecv` copies results back (`api_layer.md` §3).

At 2dea74d9 all twelve types lived in one 2179-line `PlantAPIData.F90`. At cb243228 they are split into twelve domain modules plus a module of shared scalar pointers, and `PlantAPIData.F90` is a 104-line compatibility facade: its first lines read "Compatibility facade; consumers should import their domain modules directly" (`f90src/APIData/PlantAPIData.F90:1-2`). The library builds all 14 files (`f90src/APIData/CMakeLists.txt:1-16`).

## Files, types and singletons

| File | Lines | Type (declared at) | Singleton (declared at) | Init / Destroy |
|---|---|---|---|---|
| `PlantSiteAPIData.F90` | 114 | `plant_siteinfo_type` (`:8`) | `plt_site` (`:74`) | `plt_site_Init` `:78` / `plt_site_destroy` `:107` |
| `PlantPhotosynthesisAPIData.F90` | 172 | `plant_photosyns_type` (`:8`) | `plt_photo` (`:85`) | `plt_photo_init` `:89` / `plt_photo_destroy` `:164` |
| `PlantRadiationAPIData.F90` | 104 | `plant_radiation_type` (`:8`) | `plt_rad` (`:60`) | `plt_rad_init` `:64` / `plt_rad_destroy` `:96` |
| `PlantMorphologyAPIData.F90` | 395 | `plant_morph_type` (`:8`) | `plt_morph` (`:189`) | `plt_morph_init` `:193` / `plt_morph_destroy` `:388` |
| `PlantPhenologyAPIData.F90` | 197 | `plant_pheno_type` (`:8`) | `plt_pheno` (`:98`) | `plt_pheno_init` `:102` / `plt_pheno_destroy` `:191` |
| `PlantSoilChemistryAPIData.F90` | 140 | `plant_soilchem_type` (`:8`) | `plt_soilchem` (`:42`) | `plt_soilchem_init` `:46` / `plt_soilchem_destroy` `:85` |
| `PlantAllometryAPIData.F90` | 162 | `plant_allometry_type` (`:8`) | `plt_allom` (`:60`) | `plt_allom_init` `:64` / `plt_allom_destroy` `:117` |
| `PlantBiomassAPIData.F90` | 304 | `plant_biom_type` (`:8`) | `plt_biom` (`:116`) | `plt_biom_init` `:120` / `plt_biom_destroy` `:236` |
| `PlantEnergyWaterAPIData.F90` | 157 | `plant_ew_type` (`:8`) | `plt_ew` (`:95`) | `plt_ew_init` `:99` / `plt_ew_destroy` `:150` |
| `PlantDisturbanceAPIData.F90` | 117 | `plant_disturb_type` (`:8`) | `plt_distb` (`:48`) | `plt_disturb_init` `:52` / `plt_disturb_destroy` `:87` |
| `PlantBGCRatesAPIData.F90` | 172 | `plant_bgcrate_type` (`:8`) | `plt_bgcr` (`:88`) | `plt_bgcrate_init` `:92` / `plt_bgcrate_destroy` `:165` |
| `PlantRootBGCAPIData.F90` | 298 | `plant_rootbgc_type` (`:8`) | `plt_rbgc` (`:102`) | `plt_rootbgc_init` `:106` / `plt_rootbgc_destroy` `:201` |
| `PlantAPICommonData.F90` | 29 | none | none | 16 `integer, pointer` dimension aliases |
| `PlantAPIData.F90` | 104 | none | none | `InitPlantAPIData` `:20` / `DestructPlantAPIData` `:76` |

All file and line references in the table are relative to `f90src/APIData/<File>`.

`plant_morph_type` is the only type with a third type-bound procedure, `RefreshMediumRootMeanLength` (`f90src/APIData/PlantMorphologyAPIData.F90:185`, body `:369-386`), called from `RootMod` (`f90src/Plant_bgc/RootMod.F90:295`, `:5348`) and `PlantDisturbsMod` (`f90src/Plant_bgc/PlantDisturbsMod.F90:2266`).

## What each container holds

Counts are `pointer ::` component declarations and all typed component declarations in each module at cb243228 (scalars make up the difference); the examples are the first pointer components declared.

| Container | Pointer components | All components | First pointer components | Role |
|---|---|---|---|---|
| `plt_site` | 23 | 57 | `DATAP`, `DATA`, `flag_active_pft`, `PlantElemntStoreLandscape` | column geometry, layer indices, atmosphere, PFT presence and population |
| `plt_photo` | 69 | 69 | `iPlantPhotosynsType_pft`, `SpecLeafChlAct_pft`, `LeafProtein2Chl_pft`, `LeafPEP2Protein_pft` | photosynthesis traits and per-node carboxylation state |
| `plt_rad` | 24 | 44 | `iScatteringDiffus`, `RadSWLeafAlbedo_pft`, `RadPARLeafAlbedo_pft`, `TAU_DirectSunLit` | leaf optics and canopy radiation |
| `plt_morph` | 162 | 169 | `StalkAxialResist_pft`, `RootSingleVesselArea_pft`, `tlai_day_pft`, `tsai_day_pft` | canopy, branch and root geometry; root hydraulic traits |
| `plt_pheno` | 81 | 81 | `fTgrowRootP_vr`, `ShootRootNonstElmConduts_pft`, `GrainFillRate25C_pft`, `TempOffset_pft` | phenology flags, timers, thermal adaptation, shoot-root transfer conductance |
| `plt_soilchem` | 27 | 27 | `FracBulkSOMC_vr`, `PlantElmAllocMat4Litr`, `TScal4Difsvity_vr`, `FracAirFilledSoilPoreM_vr` | soil state seen by roots |
| `plt_allom` | 44 | 44 | `CPRTS_pft`, `CNRTS_pft`, `rNCNodule_pft`, `rPCNoduler_pft` | tissue stoichiometry and growth yields |
| `plt_biom` | 101 | 101 | `TotBegVegE_pft`, `TotEndVegE_pft`, `StomatalStress_pft`, `RootMycoMassElm_pvr` | plant element pools by organ, branch, node, root layer |
| `plt_ew` | 43 | 77 | `CdH2ORootxSoil_pft`, `BulkFactor4Snow_pft`, `fSnowCanopy_pft`, `Transpiration_pft` | plant water and energy |
| `plt_distb` | 26 | 30 | `iHarvestDay_pft`, `iYearPlanting_pft`, `iPlantingDay_pft`, `iPlantingYear_pft` | planting, harvest and disturbance schedules |
| `plt_bgcr` | 67 | 73 | `PTSHTR_pft`, `RootShootExch_pvr`, `Nutruptk_fClim_rpvr`, `Nutruptk_fNlim_rpvr` | plant BGC rates and their accumulators |
| `plt_rbgc` | 85 | 85 | `canopy_growth_pft`, `TRootGasLossDisturb_col`, `trcs_Soil2plant_uptake_vr`, `trcs_Soil2plant_uptake_pvr` | root uptake kinetics, root gases, uptake fluxes |

## Which transfer routine touches which container

Number of `plt_<x>%` references in each API source file at cb243228 (a reference may be a send or a receive). The column order follows the table above.

| API file | site | photo | rad | morph | pheno | soilchem | allom | biom | ew | distb | bgcr | rbgc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `PlantColumnTransferMod.F90` | 45 | 0 | 9 | 16 | 1 | 31 | 4 | 4 | 50 | 9 | 52 | 8 |
| `PlantStateTransferMod.F90` | 11 | 45 | 8 | 53 | 43 | 0 | 12 | 61 | 42 | 35 | 29 | 30 |
| `PlantCanopyTransferMod.F90` | 0 | 25 | 0 | 60 | 59 | 0 | 2 | 54 | 2 | 0 | 4 | 2 |
| `PlantRootTransferMod.F90` | 0 | 0 | 0 | 48 | 1 | 2 | 0 | 17 | 12 | 0 | 6 | 82 |
| `PlantRootAxisTransferMod.F90` | 0 | 0 | 0 | 40 | 0 | 2 | 0 | 14 | 0 | 0 | 1 | 20 |
| `PlantTraitsTransferMod.F90` | 2 | 15 | 5 | 34 | 21 | 0 | 31 | 4 | 3 | 4 | 0 | 9 |
| `PlantCanAPI.F90` | 13 | 4 | 44 | 32 | 1 | 3 | 0 | 1 | 19 | 0 | 0 | 0 |
| `PlantAPI4Uptake.F90` | 19 | 5 | 17 | 36 | 2 | 9 | 0 | 4 | 71 | 0 | 0 | 0 |

Reading the matrix: traits reach `plt_allom`, `plt_photo`, `plt_pheno` and `plt_morph` mainly through `PlantTraitsTransferMod`, which has no receive routine; the canopy radiation path (`PlantCanAPI`) and the prescribed-phenology path (`PlantAPI4Uptake`) contain no references to `plt_allom`, `plt_distb`, `plt_bgcr` or `plt_rbgc`.

## Shared dimension pointers: `PlantAPICommonData`

`PlantAPICommonData` declares 16 `integer, pointer` scalars used as array bounds in every `Init`: `NumGrowthStages`, `MaxNumRootAxes`, `MaxNumBranches`, `JP1`, `NumOfSkyAzimuthSects1`, `jcplx`, `NumOfLeafAzimuthSectors1`, `NumCanopyLayers1`, `JZ1`, `NumLeafInclinationClasses1`, `MaxNodesPerBranch1`, `jsken`, `NumLitterGroups`, `NumOfPlantMorphUnits`, `NumOfPlantLitrCmplxs`, `jroots` (`f90src/APIData/PlantAPICommonData.F90:12-27`). They are associated with the `pltpar` record in `InitPlantAPIData` (`f90src/APIData/PlantAPIData.F90:24-41`).

## Lifecycle

`InitPlantAPIData` (`f90src/APIData/PlantAPIData.F90:20-68`) is called from `InitAlloc` (`f90src/Ecosim_mods/InitAllocMod.F90:106`). It associates the dimension pointers (`:24-41`), then calls `Init` on the twelve singletons in the order site, root BGC, BGC rates, phenology, energy and water, disturbance, allometry, biomass, soil chemistry, radiation, photosynthesis, morphology (`:43-65`), then an empty `InitAllocate` (`:67`, body `:70-74`). Each `Init` allocates its components and fills them with `spval`.

`DestructPlantAPIData` (`f90src/APIData/PlantAPIData.F90:76-101`) is called from `f90src/Main/EcoSIMDesctruct.F90:79`. It calls `Destroy` on eleven singletons; `plt_rbgc%Destroy` is not called (the same omission existed at 2dea74d9).

## Who uses it

No module in `f90src/Plant_bgc/` imports `PlantAPIData` any longer; the only two `use PlantAPIData` statements are the lifecycle imports in `f90src/Ecosim_mods/InitAllocMod.F90:48` and `f90src/Main/EcoSIMDesctruct.F90:43`. Twenty-three plant modules import the domain modules directly: `ExtractsMod`, `GrosubsMod`, `InitPlantMod`, `LitterFallMod`, `NoduleBGCMod`, `NutUptakeMod`, `PhotoSynsMod`, `PlantBalMod`, `PlantBranchMod`, `PlantDebugMod`, `PlantDisturbByFireMod`, `PlantDisturbByGrazingMod`, `PlantDisturbByTillageMod`, `PlantDisturbsMod`, `PlantMathFuncMod`, `PlantNonstElmDynMod`, `PlantPhenolMod`, `RadiationDataMod`, `RootGasMod`, `RootMod`, `StomatesMod`, `SurfaceRadiationMod`, `UptakesMod` (from `git grep -n -i -E "^\s*use (Plant[A-Za-z]*APIData|PlantAPICommonData)\b" cb243228 -- f90src/Plant_bgc`). Inside the kernels the components are usually reached through `associate` aliases, for example `RootSingleVesselRstaxial_pft => plt_morph%RootSingleVesselRstaxial_pft` in `UptakesMod` (`f90src/Plant_bgc/UptakesMod.F90:1200`).

Domain modules imported by the main kernels (module name without the `Plant` prefix and `APIData` suffix; `APICommonData` is `PlantAPICommonData`), from the `use` statements of each file in `f90src/Plant_bgc/`:

| Kernel module | Imports |
|---|---|
| `StomatesMod.F90` | APICommonData, BGCRates, Biomass, EnergyWater, Morphology, Phenology, Photosynthesis, Radiation, Site |
| `PhotoSynsMod.F90` | APICommonData, Biomass, Morphology, Phenology, Photosynthesis, Radiation, Site |
| `UptakesMod.F90` | APICommonData, Biomass, EnergyWater, Morphology, Phenology, Photosynthesis, Radiation, RootBGC, Site, SoilChemistry |
| `NutUptakeMod.F90` | Allometry, APICommonData, BGCRates, Biomass, EnergyWater, Morphology, Phenology, Photosynthesis, Radiation, RootBGC, Site, SoilChemistry |
| `RootMod.F90` | Allometry, APICommonData, BGCRates, Biomass, EnergyWater, Morphology, Phenology, Photosynthesis, RootBGC, Site, SoilChemistry |
| `GrosubsMod.F90` | Allometry, APICommonData, BGCRates, Biomass, Disturbance, EnergyWater, Morphology, Phenology, Photosynthesis, RootBGC, Site |
| `PlantBranchMod.F90` | all twelve domain modules and APICommonData |
| `PlantPhenolMod.F90` | Allometry, APICommonData, BGCRates, Biomass, Disturbance, EnergyWater, Morphology, Phenology, RootBGC, Site |
| `PlantBalMod.F90` | Allometry, APICommonData, BGCRates, Biomass, Disturbance, Morphology, Phenology, Photosynthesis, RootBGC, Site |
| `SurfaceRadiationMod.F90` | APICommonData, Biomass, EnergyWater, Morphology, Phenology, Photosynthesis, Radiation, Site, SoilChemistry |

The transfer modules of `f90src/APIs/` import the singletons they fill, for example `PlantTraitsTransferMod` imports `plt_site`, `plt_photo`, `plt_rad`, `plt_morph` (`f90src/APIs/PlantTraitsTransferMod.F90:8-11`).

## Why a separate layer

The grid arrays of `Ecosim_datatype` are indexed `(..., NY, NX)` and are shared by every subsystem. The containers here hold one column at a time, indexed by PFT slot first, and are touched only by the plant kernels between `PlantAPISend` and `PlantAPIRecv`. That gives the plant code a defined input and output surface: anything a kernel changes in a container reaches the rest of the model only if a `Receive*` routine copies it back. Traits are the clearest case: `SendPlantTraits` has no receiving counterpart (`api_layer.md` §3.1), so trait values in these containers are reset from the grid arrays every hour.

## Allocation and fill values

Every `Init` allocates components for one column and fills real components with `spval`, the missing-value constant `1.0e30` (`f90src/Utils/data_const_mod.F90:62`), and character components with blanks. For example `plt_site_Init` allocates `PlantElemntStoreLandscape(NumPlantChemElms)`, `FracSoiAsMicP_vr(0:JZ1)`, `AtmGasc(idg_beg:idg_NH3)` and `DATAP(JP1)` (`f90src/APIData/PlantSiteAPIData.F90:82-85`). A component that no `Send*` routine fills therefore holds `1.0e30` when a kernel reads it, which is a visible symptom of a missing transfer line rather than a silent zero. The grid arrays on the other side are zero-filled at allocation (`../data_types/index.md`), so the two layers use different "unset" values.

## Adding a plant parameter: the edits the live path requires

Derived from the live read path at cb243228 (the dead `ReadPlantTraitsNC` needs no edit):

1. Add the variable to the plant parameter NetCDF along `npfts`.
2. Declare and allocate a `_tab(npfts)` array in `PlantTraitTableMod` (declarations from `f90src/Ecosim_datatype/PlantTraitTableMod.F90:8`; allocation in `AllocPlantTraitTable`, `:142-281`).
3. Read it in `ReadPlantTraitTable` (`f90src/IOutils/PlantInfoMod.F90:1708-1849`). A bare `ncd_getvar` makes the name mandatory in every parameter file; guard it with `check_var` and set a default first if older files must keep working (the pattern of `f90src/Modelpars/NitroPars.F90:150-166`, `:363-364`).
4. Declare and allocate the per-PFT grid array in `PlantTraitDataType` (`InitPlantTraits`, `f90src/Ecosim_datatype/PlantTraitDataType.F90:215`) or the matching canopy or root module.
5. Copy `_tab(loc)` into it in `SetPlantTraits` (`f90src/IOutils/PlantInfoMod.F90:696-868`), and add any unit rescaling to `ReadPlantProperties` (`:507-533`).
6. Add a pointer component to the matching domain type and allocate it in that type's `Init` (this page, files table).
7. Send it in `SendPlantTraits` (`f90src/APIs/PlantTraitsTransferMod.F90:50-204`). No receive is needed for a trait.
8. Alias it in the kernel's `associate` block and use it.
9. If a derived value should be computed once, do it in STARTQ as `RootSingleVesselRstAxial_pft` is (`f90src/Ecosim_mods/StartqMod.F90:580`); note that STARTQ runs only in the first simulated year of a run, and `RootSingleVesselRstAxial_pft` does not appear in `f90src/IOutils/RestartMod.F90`.

## Where calibration-relevant values sit in the containers

| Grid array (source) | Container component | Declared at |
|---|---|---|
| `VmaxSpecRubCarboxyRef_pft` (VCMX) | `plt_photo%VmaxSpecRubCarboxyRef_pft(:)` | `f90src/APIData/PlantPhotosynthesisAPIData.F90:17` |
| `LeafProtein2Chl_pft` (CHL) | `plt_photo%LeafProtein2Chl_pft(:)` | `f90src/APIData/PlantPhotosynthesisAPIData.F90:11` |
| `SLA1_pft` (SLA1) | `plt_morph%SLA1_pft(:)` | `f90src/APIData/PlantMorphologyAPIData.F90:87` |
| `RootSingleVesselRstaxial_pft` (from ARSRA, RVSR) | `plt_morph%RootSingleVesselRstaxial_pft(:)` | `f90src/APIData/PlantMorphologyAPIData.F90:150` |
| `ShootRootNonstElmConduts_pft` (PTSHT) | `plt_pheno%ShootRootNonstElmConduts_pft(:)` | `f90src/APIData/PlantPhenologyAPIData.F90:10` |
| `PlantInitThermoAdaptZone_pft` (ZTYPI) | `plt_pheno%PlantInitThermoAdaptZone_pft(:)` | `f90src/APIData/PlantPhenologyAPIData.F90:31` |
| `HourReq4LeafOut_brch` (VRNLI) | `plt_pheno%HourReq4LeafOut_brch(:,:)` | `f90src/APIData/PlantPhenologyAPIData.F90:75` |
| `RootBiomGrosYld_pft` (DMRT) | `plt_allom%RootBiomGrosYld_pft(:)` | `f90src/APIData/PlantAllometryAPIData.F90:20` |
| `rNCRoot_pft` (CNRT) | `plt_allom%rNCRoot_pft(:)` | `f90src/APIData/PlantAllometryAPIData.F90:13` |
| `VmaxNH4Root_pft` (UPMXZH) | `plt_rbgc%VmaxNH4Root_pft(:,:)` (root type, PFT) | `f90src/APIData/PlantRootBGCAPIData.F90:31` |
| `GrossCO2Fix_pft` (CAN_GPP target source) | `plt_bgcr%GrossCO2Fix_pft(:)` | `f90src/APIData/PlantBGCRatesAPIData.F90:66` |
| `ShootElms_pft`, `RootElms_pft` (SHOOT_C, Root_C targets) | `plt_biom%ShootElms_pft(:,:)`, `plt_biom%RootElms_pft(:,:)` | `f90src/APIData/PlantBiomassAPIData.F90:82`, `:51` |
| `CanopyLeafArea_pft` (LAI target) | `plt_morph%CanopyLeafArea_pft(:)` | `f90src/APIData/PlantMorphologyAPIData.F90:61` |
| `MaxSoilLays4Root_pft` | `plt_morph%MaxSoilLays4Root_pft(:)` | `f90src/APIData/PlantMorphologyAPIData.F90:112` |

## Changes since 2dea74d9

- One 2179-line module became twelve domain modules, a common-pointer module and a facade (this page).
- Plant kernels import domain modules instead of `PlantAPIData`.
- New component and procedure for medium roots in `plant_morph_type` (`RefreshMediumRootMeanLength`).
- The calibration-relevant component `RootAxialResist_pft` of 2dea74d9 is gone; the kernel now receives `RootSingleVesselRstaxial_pft` (`f90src/APIData/PlantMorphologyAPIData.F90:150`).
