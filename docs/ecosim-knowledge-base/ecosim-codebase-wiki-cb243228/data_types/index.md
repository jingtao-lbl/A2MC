---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/Ecosim_datatype/` (33 modules), with their lifecycle callers `f90src/Ecosim_mods/InitAllocMod.F90` and `f90src/Main/EcoSIMDesctruct.F90`
**Last verified:** 2026-10-15
---

# Ecosim_datatype: the Shared State Layer

## Purpose

`f90src/Ecosim_datatype/` holds the model's grid-indexed state and flux arrays. Readers (`../io_and_forcing/`) fill them, physics modules read and update them, the API layer (`../apis/`) copies their plant slices into and out of the plant kernels, and the history and restart code reads them. Every module is a flat collection of module-level allocatable arrays with an `Init*` and a `Destruct*` routine. At cb243228 no module in this directory defines a Fortran derived type: `git grep -n -i -E "^\s*type\s*(,[^:]*)?::\s*\w+" cb243228 -- f90src/Ecosim_datatype` returns nothing, while the same pattern finds the twelve `type, public ::` declarations of `f90src/APIData/` (positive control).

## Module pattern

`SoilBGCDataType` is representative:

```fortran
real(r8),target,allocatable ::  CNH4_vr(:,:,:)      !soil NH4 content, [mg kg-1]    (SoilBGCDataType.F90:14)
...
subroutine InitSoilBGCData(NumOfPlantLitrCmplxs)    (:144-150) -> calls InitAllocate
subroutine InitAllocate(NumOfPlantLitrCmplxs)       (:154-290)
  allocate(CNH4_vr(JZ,JY,JX));     CNH4_vr=0._r8    (:164)
subroutine DestructSoilBGCData                      (:294-425) -> call destroy(...) per array
```

(`f90src/Ecosim_datatype/SoilBGCDataType.F90:14`, `:144-150`, `:154-290`, `:164`, `:294-425`.)

Conventions visible across the directory:

- **`target` attribute.** Arrays are declared `target` so the history engine and the API layer can point at them. The exception is the new `MLDataDiagType.F90`, whose 38 arrays are plain `allocatable` (`f90src/Ecosim_datatype/MLDataDiagType.F90:15-60`).
- **Element kind.** Most arrays are `real(r8)`. `RootDataType.F90` declares many arrays `real(sp)`, but `sp` is imported as an alias of `DAT_KIND_r8` (`f90src/Ecosim_datatype/RootDataType.F90:6`), so they are double precision too.
- **Units live in comments.** Each declaration carries a trailing comment with units; `d-2` means per grid cell. The comments are not checked by the compiler and some are wrong: `SoilAlbedo_col` is commented "snowpack albedo" but holds the soil-surface albedo read from `ALBS` (`f90src/Ecosim_datatype/SnowDataType.F90:15`; `f90src/IOutils/readimod.F90:440`); `RAIN(366)` and `WIND(366)` are commented `mm d-1` and `m d-1` but are used as m per day and m h-1 (`f90src/Ecosim_datatype/ClimForcDataType.F90:32-33`; `../io_and_forcing/forcing.md` §2.4).
- **Zero-based layer index.** Profiles that include the surface litter layer are allocated `(0:JZ,...)`, for example `TKS_vr` (`f90src/Ecosim_datatype/SoilHeatDataType.F90:44`) and `CPO4B_vr` (`f90src/Ecosim_datatype/SoilBGCDataType.F90:192`).

### Name suffixes

| Suffix | Indexing | Example (declaration) |
|---|---|---|
| `_col` | `(JY,JX)` column | `Eco_GPP_CumYr_col` (`f90src/Ecosim_datatype/EcosimBGCFluxType.F90:18`) |
| `_vr` | `(layer,JY,JX)` soil profile | `CNH4_vr` (`f90src/Ecosim_datatype/SoilBGCDataType.F90:14`) |
| `_pft` | `(JP,JY,JX)` or with a leading element or root-type index | `GrossCO2Fix_pft` (`f90src/Ecosim_datatype/PlantDataRateType.F90:33`) |
| `_brch` | `(branch,JP,JY,JX)` | `LeafAreaLive_brch` (`f90src/Ecosim_datatype/PlantTraitDataType.F90:58`) |
| `_pvr`, `_rpvr` | per PFT and layer; per root type, PFT and layer | `RootShootExch_pvr` (`f90src/Ecosim_datatype/RootDataType.F90:14`), `Root1stActStructElms_rpvr` (`:122`) |
| `_raxes` | per root axis | `NRoot1stTipLay_raxes` (`f90src/Ecosim_datatype/RootDataType.F90:15`) |
| `_lnode` | per canopy layer and node | `CanopyLeafArea_lnode` (`f90src/Ecosim_datatype/CanopyDataType.F90:172`) |
| `_snvr` | snow layers | `VLSnowHeatCapM_snvr` (`f90src/Ecosim_datatype/SnowDataType.F90:12`) |
| `_2DH`, `_3D` | lateral exchange between grid cells; 3 directions | `TXGridSurfRunoff_2DH` (`f90src/Ecosim_datatype/SoilWaterDataType.F90:10`), `DLYR_3D(3,0:JZ,JY,JX)` (`f90src/Ecosim_datatype/GridDataType.F90:12`, `:42`) |
| `_CumYr`, `_beg` | year-to-date accumulator; start-of-step snapshot | `Eco_GPP_CumYr_col`, `trcg_TotalMass_beg_col` (`f90src/Ecosim_datatype/SoilBGCDataType.F90:37`) |
| `_tab` | `(npfts)` record of the plant parameter file | `PlantInitThermoAdaptZone_tab` (`f90src/Ecosim_datatype/PlantTraitTableMod.F90:26`) |

## Files by domain (33)

Line counts and the number of `allocatable` declarations are at cb243228. "Init / Destruct" are the lifecycle routines with their header lines.

### Plant traits, parameters and rates

| File | Lines | Alloc. decl. | Init / Destruct | Holds |
|---|---|---|---|---|
| `PlantTraitTableMod.F90` | 418 | 131 | `AllocPlantTraitTable` `:142` / `DestructPlantTraitTable` `:286` | one `_tab(npfts)` vector per plant-file variable (integer type flags and real traits), filled once by `ReadPlantTraitTable` |
| `PlantTraitDataType.F90` | 615 | 193 | `InitPlantTraits` `:215` / `DestructPlantTraits` `:417` | per-PFT copies of the plant traits, e.g. `AlphaVesselAxialResist_pft` (`:108`), `RootSingleVesselRstaxial_pft` (`:107`), `PlantInitThermoAdaptZone_pft` (`:98`), litter allocation fractions |
| `CanopyDataType.F90` | 619 | 198 | `InitCanopyData` `:215` / `DestructCanopyData` `:421` | canopy state and photosynthesis traits, e.g. `SpecLeafChlAct_pft`, `LeafProtein2Chl_pft`, `CanopyCi2CaRatio_pft` (allocated `:298-301`), shoot and leaf element pools (`:134-135`) |
| `PlantDataRateType.F90` | 440 | 135 | `InitPlantRates` `:151` / `DestructPlantRates` `:305` | plant fluxes: `CanopyGrosRCO2_pft`, `GrossCO2Fix_pft` (`:33`), `NetPrimProduct_pft` (`:42`), `Eco_NEE_col` |
| `RootDataType.F90` | 468 | 145 | `InitRootData` `:162` / `DestructRootData` `:316` | root morphology and pools; root traits with a root-type index `(jroots,JP,JY,JX)` such as `Root1stMaxRadius_pft` (`:223`), `VmaxNH4Root_pft` (`:205`); `RootElms_pft` (`:118`) |
| `CanopyRadDataType.F90` | 92 | 13 | `InitCanopyRad` `:28` / `DestructCanopyRad` `:75` | leaf-angle geometry `SineLeafAngle`, `CosineLeafAngle`, leaf angle classes |
| `PlantMgmtDataType.F90` | 112 | 25 | `InitPlantMngmtData` `:38` / `DestructPlantMngmtData` `:79` | `flag_active_pft`, `THIN_pft`, harvest types and fractions filled by the management reader |

### Soil biogeochemistry and chemistry

| File | Lines | Alloc. decl. | Init / Destruct | Holds |
|---|---|---|---|---|
| `SoilBGCDataType.F90` | 427 | 127 | `InitSoilBGCData` `:144` / `DestructSoilBGCData` `:294` | soil solutes, gases, surface fluxes (`SurfGasEmiss_all_flx_col`, `:49`), mass snapshots |
| `MicrobialDataType.F90` | 205 | 56 | `InitMicrobialData` `:73` / `DestructMicrobialData` `:144` | microbial biomass `mBiomeHeter_vr`, O2 and substrate demands |
| `SOMDataType.F90` | 150 | 37 | `InitSOMData` `:53` / `DestructSOMData` `:107` | initial surface-residue and SOM pools `RSC_vr`, `RSN_vr`, ... |
| `AqueChemDatatype.F90` | 231 | 61 | `InitAquaChem` `:86` / `DestructAquaChem` `:167` | aqueous chemistry contents `CAL_vr`, `CFE_vr`, ... |
| `FertilizerDataType.F90` | 75 | 11 | `InitFertilizerData` `:28` / `DestructFertilizerData` `:55` | broadcast and band fertilizer pools |
| `ChemTranspDataType.F90` | 114 | 19 | `InitChemTranspData` `:41` / `DestructChemTranspData` `:87` | temperature-scaled diffusivity, dispersivity `DISP_3D` |
| `NumericalAuxMod.F90` | 42 | 2 | `InitNumericAux` `:20` / `DestructNumericAux` `:32` | dribbling buffers for sub-step transport |

### Soil physics, snow and surface

| File | Lines | Alloc. decl. | Init / Destruct | Holds |
|---|---|---|---|---|
| `SoilWaterDataType.F90` | 355 | 107 | `InitSoilWater` `:120` / `DestructSoilWater` `:242` | soil water, runoff, `QEvap_CumYr_col` (`:87`) |
| `SoilHeatDataType.F90` | 91 | 21 | `InitSoilHeatData` `:37` / `DestructSoilHeatData` `:65` | soil temperature `TKS_vr`, freeze-thaw fluxes |
| `SoilPhysDataType.F90` | 117 | 31 | `InitSoilPhysData` `:44` / `DestructSoilPhysData` `:81` | slope, hydraulic properties, layer PAR `PAR_RAD_vr` |
| `SoilPropertyDataType.F90` | 121 | 28 | `InitSoilProperty` `:43` / `DestructSoilProperty` `:87` | initial soil properties `CORGCI_vr`, `POROSI_vr`, texture |
| `SnowDataType.F90` | 258 | 74 | `InitSnowData` `:90` / `DestructSnowData` `:176` | snowpack state and fluxes; `SoilAlbedo_col` (`:15`) |
| `SurfSoilDataType.F90` | 84 | 20 | `InitSurfSoilData` `:33` / `DestructSurfSoilData` `:59` | snow-cover fractions, surface radiation |
| `SurfLitterDataType.F90` | 105 | 22 | `InitSurfLitter` `:37` / `DestructSurfLitter` `:76` | surface litter properties, tillage mixing |
| `LandSurfDataType.F90` | 86 | 20 | `InitLandSurfData` `:35` / `DestructLandSurfData` `:61` | roughness, displacement height |
| `SedimentDataType.F90` | 122 | 28 | `InitSedimentData` `:45` / `DestructSedimentData` `:88` | erosion state `TSED_col` |
| `GridDataType.F90` | 94 | 22 | `InitGridData` `:37` / `DestructGridData` `:66` | layer depths and thicknesses `CumDepz2LayBottom_vr`, `DLYR_3D` |

### Forcing, management flags, aggregates and control

| File | Lines | Alloc. decl. | Init / Destruct | Holds |
|---|---|---|---|---|
| `ClimForcDataType.F90` | 369 | 98 | `InitClimForcData` `:156` / `DestructClimForcData` `:267` | forcing arrays `TMPX(366)` ... `PBOT_hrly(24,366)` (`:29-43`, fixed size), GHG monthly arrays (`:26-28`), warming scalars, climate-change accumulators |
| `IrrigationDataType.F90` | 242 | 65 | `InitIrrigation` `:86` / `DestructIrrigation` `:169` | irrigation schedule `IIRRA`, `RRIG` |
| `FlagDataType.F90` | 77 | 16 | `InitFlagData` `:34` / `DestructFlagData` `:56` | integer flags `IYTYP`, `iSoilDisturbType_col`, `IsPlantActive_pft` |
| `EcosimBGCFluxType.F90` | 100 | 24 | `InitEcosimBGCFluxData` `:41` / `DestructEcosimBGCFluxData` `:71` | column energy and carbon accumulators `Eco_GPP_CumYr_col` (`:18`), `Eco_AutoR_CumYr_col` (`:19`), `Eco_HR_CumYr_col` (`:21`) |
| `EcoSimSumDataType.F90` | 68 | 2 | `InitEcoSimSum` `:48` / `DestructEcoSimSum` `:62` | landscape totals `SurfGas_lnd`, `PlantElemntStoreLandscape` |
| `BalanceCheckDataType.F90` | 39 | 4 | `InitBalanceCheckData` `:20` / `DestructBalanceCheckData` `:30` | closure errors `WaterErr_col`, `HeatErr_col` |
| `MLDataDiagType.F90` | 153 | 38 | `InitMLDataType` `:60` / `DestructMLDataType` `:107` | new: 0-30 cm and 0-60 cm summaries for machine-learning diagnostics |
| `EcoSIMCtrlDataType.F90` | 66 | 5 | `InitEcoSIMCtrlData` `:41` / `DestructEcoSIMCtrlData` `:53` | numerical thresholds `ZEROS` (`:12`), `ZERO4Groth_pft`, run counters |
| `EcoSIMHistMod.F90` | 60 | 6 | `InitEcoSIMHistData` `:30` / `DestructEcoSIMHistData` `:45` | PFT name keys `DATAP` (`:12`, `character(len=16)`), used to look up the plant table |

## Changes since 2dea74d9

`git diff --stat 2dea74d9 cb243228 -- f90src/Ecosim_datatype` reports 35 files changed, 580 insertions and 150 deletions (the count includes `CMakeLists.txt` and file-mode changes). Content changes that matter to readers of the plant parameters:

| Change | Arrays | Declared at cb243228 |
|---|---|---|
| root axial resistance re-parameterised | removed `RootAxialResist_pft`; added `AlphaVesselAxialResist_pft` (ARSRA), `RootVesselRadius_pft` (RVSR), `RootSingleVesselRstaxial_pft` (derived in STARTQ) | `f90src/Ecosim_datatype/PlantTraitDataType.F90:107-108` and the `RootVesselRadius_pft` declaration in the same file |
| medium-root and coarse-root traits | added `MediumRootBranchFreq_pft` (MRTFQ), `rECLiveCRoot_pft`, `rECDeadCRoot_pft` (CNLCRT, CPLCRT, CNDCRT, CPDCRT) | `f90src/Ecosim_datatype/RootDataType.F90:226` (allocation); `f90src/Ecosim_datatype/PlantTraitDataType.F90:271-272` (allocation) |
| stalk and stem traits | added `StalkAxialResist_pft` (RSSA), `enh_cyto_pft` (CYTOS), `StemSpecVolume_pft` (from STDENS) | `f90src/Ecosim_datatype/PlantTraitDataType.F90` |
| machine-learning diagnostics | new module `MLDataDiagType.F90` | `f90src/Ecosim_datatype/MLDataDiagType.F90:1-153` |

Line-count growth is concentrated in `PlantTraitDataType.F90` (556 to 615), `RootDataType.F90` (410 to 468), `CanopyDataType.F90` (583 to 619), `PlantTraitTableMod.F90` (386 to 418), `ClimForcDataType.F90` (341 to 369) and `MicrobialDataType.F90` (181 to 205).

## Lifecycle

`InitAlloc` (`f90src/Ecosim_mods/InitAllocMod.F90:11-155`) runs first in `InitModules` (`f90src/Main/InitEcoSIM.F90:34`) and calls, among others, `InitPlantTraitTable` when `plant_model` is on (`f90src/Ecosim_mods/InitAllocMod.F90:73`; sizes the `_tab` arrays from the plant file), `InitGridData` (`:76`), `InitPlantAPIData` (`:106`), `InitSoilBGCData` (`:112`), `InitPlantTraits` (`:118`), `InitRootData(2)` (`:124`), `InitClimForcData` (`:126`), `InitMLDataType` (`:148`). `f90src/Main/EcoSIMDesctruct.F90` calls the matching `Destruct*` routines (`:61-139`), including `DestructPlantTraitTable` (`:95`) and `DestructMLDataType` (`:137`).

## How the layer is used

1. **Readers write it.** `readi` fills grid, soil and site arrays; `ReadPlantTraitTable` fills `PlantTraitTableMod`; `SetPlantTraits` copies one table record into `PlantTraitDataType`, `CanopyDataType` and `RootDataType` per PFT each year (`f90src/IOutils/PlantInfoMod.F90:696-868`); the management readers fill `PlantMgmtDataType`, `FlagDataType`, `FertilizerDataType`, `IrrigationDataType`.
2. **Physics outside the plant and microbe kernels reads and writes it directly** by `use`-ing the modules (hydrology, heat, transport, redistribution).
3. **The plant kernels almost never use it.** The plant modules in `f90src/Plant_bgc/` work on the `plt_*` containers of `f90src/APIData/`; the only imports of this directory from `f90src/Plant_bgc/` are `CanopyRadDataType` in `InitVegBGC` (`f90src/Plant_bgc/InitVegBGC.F90:14`) and the scalars `iYearCurrent` and `DazCurrYear` of `EcoSIMCtrlDataType` (`f90src/Plant_bgc/LitterFallMod.F90:227`, `f90src/Plant_bgc/PlantDisturbsMod.F90:7`); `PlantAPISend` and `PlantAPIRecv` copy between the two every hour (`../apis/api_layer.md`). The microbial kernel receives per-layer copies through `MicAPISend` / `MicAPIRecv`.
4. **Output reads it.** `update_hist_columns`, `update_hist_soil` and `update_hist_plants` divide extensive arrays by the column area (`../io_and_forcing/history_and_restart.md` §2); `RestartMod` writes and reads them with `restartvar`.

## Pitfalls when reading this layer

- **Zero is the allocation default.** Every allocator zero-fills, e.g. `RootSingleVesselRstaxial_pft=0._R8` (`f90src/Ecosim_datatype/PlantTraitDataType.F90:312`). A trait that no reader or initialiser assigns stays 0 rather than failing; `RootSingleVesselRstaxial_pft` gets its value only in STARTQ (`f90src/Ecosim_mods/StartqMod.F90:580`).
- **PFT keys are 6 characters inside a 16-character field.** `DATAP` is `character(len=16)` (`f90src/Ecosim_datatype/EcoSIMHistMod.F90:12`), but the plant-table lookup uses `DATAP(NZ,NY,NX)(1:6)` (`f90src/IOutils/PlantInfoMod.F90:711`).
- **Fixed 366-day forcing arrays** in `ClimForcDataType` are not allocatable (`f90src/Ecosim_datatype/ClimForcDataType.F90:29-43`); readers pad day 366 in non-leap years.
- **Names that look single precision are not.** `real(sp)` in `RootDataType.F90` resolves to `DAT_KIND_r8` (`:6`).
- **Two places for plant traits.** The model keeps one `_tab` record per PFT key and one `_pft` copy per PFT slot; editing a `_tab` value after `SetPlantTraits` has run affects the next year, editing a `_pft` value affects only the current year (`f90src/IOutils/PlantInfoMod.F90:489`, run every year from `readq`).

## Where the 60 calibration names land

| Destination module | Names |
|---|---|
| `PlantTraitTableMod` then `PlantTraitDataType` | ARSRA, CNDCRT, CNLCRT, CNLF, CNRSV, CNRTLIG, CNSHE, CNSTK, CNWL, CNWR, CPDCRT, CPLCRT, CPLF, CPWL, CTC, DMLF, DMRSV, DMSTK, GROUPX, OSMO, PB, SLA1, XPPD, XRLA, XRNI, XTLI, ZTYPI; VRNLI and VRNXI via `HourReq4LeafOut_brch`, `HourReq4LeafOff_brch` |
| `PlantTraitTableMod` then `CanopyDataType` | CHL, ETMX, FCO2, RCS, RSMX, RUBP, VCMX, VOMX, XKCO2 |
| `PlantTraitTableMod` then `RootDataType` | CNRT, DMRT, MRTFQ, PORT, PR, PTSHT, RRAD1M, RRAD2M, RSRR, RTFQ, UPMXPO, UPMXZH, UPMXZO |
| not read (dead reader only) | RSRA |
| `f90src/Modelpars/NitroPars.F90` module variables (not this directory) | CKC, DCKM0, OMGR, RMOM, SPOMC, SPORC, SPOSC, VMXO |

The exact Fortran variable, reader line and copy line for each name are in the reader map at the end of `../io_and_forcing/input_readers.md`.
