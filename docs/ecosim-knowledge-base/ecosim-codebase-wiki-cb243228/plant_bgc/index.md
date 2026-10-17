---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/Plant_bgc/`, `f90src/Prescribed_pheno/`, plant parts of `f90src/APIs/PlantMod.F90`, `f90src/IOutils/PlantInfoMod.F90`, `f90src/Ecosim_mods/StartqMod.F90`
**Last verified:** 2026-10-15
---

# Plant biogeochemistry subsystem

This subsystem holds every living-plant process: phenology and the growth-stage calendar, branching, photosynthesis and stomatal conductance, autotrophic respiration, allocation and organ growth, tissue stoichiometry, senescence and litterfall, roots and root growth, root hydraulics and water uptake, nutrient and O2 uptake, nodule N2 fixation, root gas exchange, disturbance (harvest, grazing, fire, tillage) and the hourly plant mass balance. A prescribed-phenology mode replaces dynamic phenology and growth with interpolated LAI/SAI and a fixed root profile.

Plant state lives in the `plt_*` API types (`plt_pheno`, `plt_morph`, `plt_biom`, `plt_allom`, `plt_photo`, `plt_rad`, `plt_ew`, `plt_rbgc`, `plt_bgcr`, `plt_distb`, `plt_site`, `plt_soilchem`), imported by every module here (e.g. `f90src/Plant_bgc/GrosubsMod.F90:16-25`) and filled from the column arrays by `PlantAPISend` and returned by `PlantAPIRecv` (`f90src/APIs/PlantAPI.F90:70-102`, `:40-65`). Routines read them through Fortran `associate` blocks.

## 1. Pages

| Page | Covers |
|---|---|
| [`phenology.md`](phenology.md) | `PhenologyUpdate`, planting and emergence, branch and root-axis initiation, derived thresholds (VRNLI, VRNXI, GROUPX, XTLI, ZTYPI), node initiation and leaf appearance (XRNI, XRLA), the growth-stage calendar and photoperiod (XDL, XPPD), leaf-out/leaf-off rules by phenology type (CTC), what the leaf-out status gates, annual termination, seasonal resets, prescribed-phenology mode |
| [`growth_and_allocation.md`](growth_and_allocation.md) | branch growth order, stage-prescribed partitioning, organ growth yields (DMLF, DMSTK, DMRSV), the N/P-limited growth budget, tissue stoichiometry (CNLF, CPLF, CNSHE, CNSTK, CNRSV), leaf/sheath/internode expansion (SLA1), the leaf-protein co-limitation (CNWL, CPWL), senescence and remobilization, shoot nonstructural transfers, grain fill, standing dead, and the producing equations of LEAF_C_pft, LAI_xstk_pft, SHOOT_C_pft, Plant_C_pft and NPP_pft |
| [`photosynthesis_and_respiration.md`](photosynthesis_and_respiration.md) | C3 and C4 photosynthesis from leaf protein, chlorophyll and enzyme fractions, stomatal conductance, canopy and maintenance respiration |
| [`roots_and_uptake.md`](roots_and_uptake.md) | root architecture and layer indices, root sinks, root growth and respiration (DMRT), root death and the root clamp, shoot-root nonstructural exchange (PTSHT), root hydraulics (RRAD1M, RRAD2M, PORT, RSRR, ARSRA, RVSR, RSSA; RSRA inert), water uptake, mineral nutrient uptake (UPMX*, UPKM*), exudation, root stoichiometry (CNRT, CPRT, CNWR and coarse-root ratios), cytokinin (CYTOS), and the plant mass balance with `guard_floor_dying_stand` and `conserve_root_clamp` |

## 2. Source-file inventory

### `f90src/Plant_bgc/` (25 Fortran files)

| File (lines) | Public entities | Purpose |
|---|---|---|
| `ExtractsMod.F90` (430) | `extracts` (`:34`) | aggregates the hour's plant-soil exchanges into column arrays |
| `GrosubsMod.F90` (736) | `GrowPlants` (`:61`) | per-PFT growth driver: `GrowOnePlant` (`:261`), `StagePlantForGrowth` (`:340`), `AccumulateStates` (`:566`), `Live2DeadTransformation` (`:125`, standing-dead decay and the NPP assignment) |
| `InitPlantMod.F90` (1,314) | `StartPlants`, `InitPlantPhenoMorphoBio`, `InitRootMychorMorphoBio`, `ApplySeedBank`, `SeedDeposition` (`:30-34`) | re-initialises a PFT on its planting day (`StartPlants`, `:38`, called from `set_plant_flags`), seed bank and seed rain |
| `InitVegBGC.F90` (83) | `InitIrradianceGeometry` (`:13`) | sky azimuth/zenith tables for canopy radiation |
| `LitterFallMod.F90` (1,064) | `ResetDeadPlant`, `ReSeedPlants`, `SetDeadPlant` (`:24-26`) | dead-branch and dead-root litterfall, plant death flags, reseeding |
| `NoduleBGCMod.F90` (880) | `CanopyNoduleBiochemistry` (`:28`), `RootNodulBiochemistry` (`:425`) | canopy and root nodule N2 fixation |
| `NutUptakeMod.F90` (1,578) | `PlantNutientO2Uptake`, `ZeroNutrientUptake` (`:32-33`) | O2, NH4, NO3, H2PO4, HPO4 uptake and exudation |
| `PhotoSynsMod.F90` (572) | `ComputeGPP` (`:454`) | node and canopy-layer CO2 fixation, C3 and C4 |
| `PlantBalMod.F90` (949) | `SumPlantBiome`, `EnterPlantBalance`, `ExitPlantBalance`, `CheckPlantBalanceZ`, `SumCanopyBiome`, `SumRootBiome`, ... (`:26-37`) | biomass sums behind the history variables and the hourly C/N/P balance check |
| `PlantBranchMod.F90` (4,188) | `GrowOneBranch` (`:34`, `:47`) | branch growth: partitioning, yields, organ growth, expansion, senescence, remobilization, grain fill, seasonal resets, canopy layering (23 routines) |
| `PlantDebugMod.F90` (110) | `PrintRootTracer`, `PrintRootBiomass`, `RootMassBalCheck` (`:20-21`) | debug output |
| `PlantDisturbByFireMod.F90` (525) | `StageRootRemovalByFire`, `AbvGrndLiterFallByFire`, `AbvgBiomRemovalByFire`, `ShootBiomRemovalByFire`, `InitPlantFireMod`, `RootRemovalLbyFire` (`:22-27`) | fire removal and fire litter |
| `PlantDisturbByGrazingMod.F90` (473) | `AbvgBiomRemovalByGrazing`, `RemoveStandDeadByGrazing`, `ApplyBiomRemovalByGrazing`, `CutBranchNonstalByGrazing`, `GrazingPlant` (`:20-24`) | grazing removal |
| `PlantDisturbByTillageMod.F90` (586) | `RemoveBiomByTillage` (`:27`) | tillage |
| `PlantDisturbsMod.F90` (2,336) | `RemoveBiomassByDisturbance` (`:297`), `InitPlantDisturbance`, `StageDisturbances` (`:54-56`) | disturbance dispatch, harvest (`RemoveBiomByHarvest`, `:744`), cut-branch reset (`:987`), annual false-break death (`RemoveDeadAnnual`, `:116`) |
| `PlantMathFuncMod.F90` (688) | (module functions, no `public` list) | Arrhenius growth and maintenance temperature functions (`:118-178`), turgor function `fRespWatSens` (`:333`), type predicates (`is_plant_woody_vascular` `:270`, `is_root_bryophyte` `:287`, `is_drought_deciduos` `:575`, `is_cold_deciduos` `:584`), solute-uptake kernel (`:180`) |
| `PlantNonstElmDynMod.F90` (1,052) | `PlantNonstElmTransfer` and five transfer routines (`:28-33`) | nonstructural C, N, P transfers among branches, stalk reserve, seasonal storage and roots |
| `PlantPhenolMod.F90` (1,533) | `PhenologyUpdate` (`:42`, `:46`) | phenology driver and stage routines |
| `RadiationDataMod.F90` (84) | `InitRadiationData`, `DestroyRadiationData` (`:27-28`) | canopy-layer optical work arrays (new since 2dea74d9) |
| `RootGasMod.F90` (828) | `RootSoilGasExchange` (`:25`) | root-soil gas exchange; called from `NutUptakeMod.F90:256` |
| `RootMod.F90` (6,260) | `RootBGCModel` (`:30`, `:35`) | root sinks, root growth, respiration, death, cytokinin, nodules |
| `StomatesMod.F90` (1,071) | `StomatalDynamics` (`:202`), `PhotosynsDiag` (`:31`) | enzyme and chlorophyll pools from leaf protein, phenology gate on photosynthesis, minimum stomatal resistance |
| `SurfaceRadiationMod.F90` (1,925) | `CanopyConditionModel` (`:49`) | canopy layering and short-wave/PAR transfer |
| `UptakePars.F90` (60) | parameters only | root uptake constants |
| `UptakesMod.F90` (1,645) | `RootUptakes` (`:51`), `InitUptake` | canopy water/energy iteration, hydraulics, uptake driver, canopy growth temperature functions (`SetCanopyGrowthFuncs`, `:1567`) |

### `f90src/Prescribed_pheno/` (1 file)

| File (lines) | Public entities | Purpose |
|---|---|---|
| `PrescribePhenolMod.F90` (366) | `GetRootProfile`, `SetCanopyProfile`, `PrescribePhenologyInterp` (`:50-52`) | prescribed LAI/SAI/height interpolation (`:185-320`), uniform canopy profile (`:132-182`), Jackson beta root profile (`:322-365`); see [`phenology.md`](phenology.md) section 11 |

## 3. Hourly call flow

`PlantModel` (`f90src/APIs/PlantMod.F90:37-107`) is called once per hour from the driver (`drivers/ecosim/EcoSIMAPI.F90:73`). In dynamic mode it runs, per column:

```
PrepLandscapeGrazing                                  PlantMod.F90:52-55
PlantAPISend                                          :71      PlantAPI.F90:70
EnterPlantBalance                                     :73      PlantBalMod.F90:686  (zeroes the hour's fluxes via ZeroGrosub, :734)
SeedDeposition  (first hour of the day)               :78-81   InitPlantMod.F90:1270
PhenologyUpdate                                       :82      PlantPhenolMod.F90:46
  set_plant_flags -> StartPlants on planting day      PlantPhenolMod.F90:83, :225, :256
  FindMainBranchNumber, StagePlantPhenology, TestPlantEmergence, root_shoot_branching   :89-95
  Emerged_plant_Phenology -> live_branch_phenology, branch_specific_phenology            :97-99, :139, :158
ROOTUPTAKES                                           :85      UptakesMod.F90:51
  PhotosynsDiag                                       UptakesMod.F90:143   StomatesMod.F90:31
  StomatalDynamics                                    :149     StomatesMod.F90:202
  CalcPlantHydroResistance, canopy water iteration    :174, ...
  SetCanopyGrowthFuncs                                :225     (TKGroth, fTCanopyGroth with TempOffset)
  PlantNutientO2Uptake -> RootSoilGasExchange         :227     NutUptakeMod.F90:256
GROWPLANTS                                            :88      GrosubsMod.F90:61
  GrowOnePlant                                        GrosubsMod.F90:104
    StagePlantForGrowth                               :308
    GrowOneBranch (each branch)                       :314     PlantBranchMod.F90:47 (order on growth_and_allocation.md section 1)
      UpdatePhotosynthates -> ComputeGPP              PlantBranchMod.F90:147, :857   PhotoSynsMod.F90:454
    RootBGCModel                                      :326     RootMod.F90:35
    PlantNonstElmTransfer                             :328     PlantNonstElmDynMod.F90:642
  RemoveBiomassByDisturbance                          :106     PlantDisturbsMod.F90:297
  ResetDeadPlant                                      :109     LitterFallMod.F90:30
  AccumulateStates (every PFT)                        :113     GrosubsMod.F90:566
  Live2DeadTransformation                             :117     GrosubsMod.F90:125
EXTRACTs                                              :91      ExtractsMod.F90:34
ReSeedPlants                                          :93      LitterFallMod.F90:103
ExitPlantBalance -> CheckPlantBalanceZ                :95      PlantBalMod.F90:740
PlantAPIRecv                                          :99      PlantAPI.F90:40
```

Canopy radiation runs separately, before `PlantModel` in the hour, through `PlantCanopyRadsModel` (`PlantMod.F90:127-140`, called from `f90src/Modelforc/Hour1Mod.F90:201`), which wraps `CanopyConditionModel` (`PlantMod.F90:136`; `SurfaceRadiationMod.F90:49`).

In prescribed-phenology mode (`ldo_sp_mode = .true.`, `f90src/Modelconfig/EcoSIMCtrlMod.F90:80`) `PlantModel` runs only `PlantUptakeAPISend`, `ROOTUPTAKES`, `extracts` and `PlantUPtakeAPIRecv` (`PlantMod.F90:60-68`); there is no phenology, no growth and no balance check. `PrescribePhenologyInterp` sets LAI/SAI daily (`f90src/Modelforc/DayMod.F90:85`) and `CanopyConditionModel` calls `SetCanopyProfile` instead of layering the dynamic canopy (`SurfaceRadiationMod.F90:61-63`).

Two ordering facts matter for outputs. The NPP of `Live2DeadTransformation` is evaluated before `ExitPlantBalance` assigns `GrossResp_pft`, so NPP_pft equals gross fixation ([`growth_and_allocation.md`](growth_and_allocation.md) section 12). Uptake rates computed in `ROOTUPTAKES` are credited to root pools inside `RootBGCModel`, after branch growth ([`roots_and_uptake.md`](roots_and_uptake.md) section 1).

## 4. Initialisation and the trait reader

The live plant-parameter reader is `ReadPlantTraitTable` (`f90src/IOutils/PlantInfoMod.F90:1708-1849`, called from `f90src/Main/InitEcoSIM.F90:37` when the plant model is on and not ATS-coupled); `SetPlantTraits` copies the per-PFT values from its tables (`PlantInfoMod.F90:696-868`) and `ReadPlantProperties` derives the phenology thresholds every year (`:472-537`; [`phenology.md`](phenology.md) section 3). A second, per-PFT reader `ReadPlantTraitsNC` (`:540-694`) has no caller. Plant state is initialised by `startq` at the start of the first simulated year (`drivers/ecosim/EcoSIMAPI.F90:437`; `f90src/Ecosim_mods/StartqMod.F90:34-113`) and again for a PFT on each planting day by `StartPlants` (`InitPlantMod.F90:38-158`), both running the same sequence of shoot, litter-fraction, thermal-acclimation, dimension, phenology, mass-balance, root, seed and heat initialisations (`StartqMod.F90:65-81`; `InitPlantMod.F90:116-132`).

## 5. Plant structure

```
PFT NZ (1..NP)
 |-- branches NB (1..NumOfBranches_pft; at most BranchNumMax(IBTYP) = 5 for IBTYP 0, else 1)
 |    |-- organs: leaf, petiole/sheath, stalk, stalk reserve, husk, ear, grain (PlantBranchMod.F90:36-42)
 |    |-- nodes K (up to MaxNodesPerBranch = 25): leaf, petiole, internode and protein masses
 |    |-- branch nonstructural C, N, P
 |    `-- growth-stage calendar iPlantCalendar_brch(1:10)
 |-- seasonal storage SeasonalNonstElms_pft
 `-- roots: structural axes NR, primary and fine axes per soil layer L,
            root type N = 1 plant root, 2 mycorrhiza (roots_and_uptake.md section 2)
```

The branch cap is `BranchNumMax(0:3) = (5,1,1,1)` (`PlantPhenolMod.F90:40`, `:339`); `MaxNumBranches = 10` and `MaxNodesPerBranch = 25` are grid constants (`f90src/Mesh/GridConsts.F90:17`, `:29`); stage ids are in `f90src/Modelconfig/ElmIDMod.F90:130-140`, and the calendar is allocated for stages 1 to `NumGrowthStages = 10` (`f90src/Ecosim_datatype/PlantTraitDataType.F90:390`; `GridConsts.F90:18`), so the planting stage id 0 is never stored.

## 6. Where the calibration parameters live

| Parameter(s) | Page | Mechanism (curated seed) |
|---|---|---|
| VRNLI, VRNXI, XRNI, XRLA, XTLI, GROUPX, XPPD, XDL, CTC, PB, ZTYPI | [`phenology.md`](phenology.md) section 12 | Node_Leaf_Phenology |
| DMLF, DMSTK, DMRSV | [`growth_and_allocation.md`](growth_and_allocation.md) section 14 | Stage_Prescribed_Allocation |
| SLA1 | [`growth_and_allocation.md`](growth_and_allocation.md) section 14 | Leaf_Area_Expansion |
| CNLF, CPLF, CNWL, CPWL | [`growth_and_allocation.md`](growth_and_allocation.md) section 14 | Leaf_Protein_Colimitation, Prescribed_Tissue_Stoichiometry |
| CNSHE, CNSTK, CNRSV | [`growth_and_allocation.md`](growth_and_allocation.md) section 14 | Prescribed_Tissue_Stoichiometry |
| IWTYP, ISTYP, IDTYP, IPTYP, IBTYP, IGTYP, ICTYP, IRTYP | [`phenology.md`](phenology.md) section 10 | Plant_Functional_Type_Switches |
| DMRT, PR, RTFQ, MRTFQ, PTSHT, RRAD1M, RRAD2M, PORT, RSRR, ARSRA, RVSR, RSSA, RSRA (inert), CNRT, CPRT, CNWR, coarse-root ratios, UPMXZH, UPMXZO, UPMXPO, UPKMPO, CYTOS | [`roots_and_uptake.md`](roots_and_uptake.md) | Root_* and uptake mechanisms |
| photosynthesis, stomatal and respiration parameters (e.g. VCMX, RUBP, CHL, ETMX, RSMX, read at `PlantInfoMod.F90:1736`, `:1743`, `:1747`, `:1746`, `:1813`) | [`photosynthesis_and_respiration.md`](photosynthesis_and_respiration.md) | Grant_Rubisco_C3_Kinetics, PEP_C4_Refixation, Turgor_Based_Stomatal_Stress |

## 7. History outputs produced in this subsystem (selection)

| Output | Producing variable | Line |
|---|---|---|
| LEAF_C_pft, PetolSheth_C_pft, STALK_C_pft, RESERVE_C_pft | branch sums of structural organ C | `f90src/IOutils/HistData/HistUpdatePlant.F90:196-199` |
| SHOOT_C_pft, Plant_C_pft | `ShootElms_pft`, `ShootElms_pft + RootElms_pft` | `:191-193` |
| LAI_xstk_pft, LAIstk_pft | `CanopyLeafArea_pft`, `LeafStalkAreaAct_pft` | `:214`, `:171` |
| NPP_pft, CAN_GPP_pft, AUTO_RESP_pft | `NetPrimProduct_pft`, `GrossCO2Fix_pft`, `GrossResp_pft` | `:94`, `:155`, `:215` |
| CAN_GROWTH_pft, SSTORED_C_pft | `canopy_growth_pft`, `SeasonalNonstElms_pft` | `:158`, `:212` |
| RNodeAppear_pft, RLeafAppear_pft, ShootNodeNumber_pft, MainBranchNodeNumber_pft, BRANCH_NO_pft | phenology counters | `:194-195`, `:115-116`, `:272` |
| CanPhenol_TSTRESS_pft, CanPhenol_WSTRESS_pft | `TFNP`, `WFNG*OFNG` | `:172-173` |
| fLEAF_CN_pft | `1/fNCLFW_pft` (area-weighted realised leaf N:C of new growth) | `:240`; `GrosubsMod.F90:654-667` |
| Growth_Stage_pft | highest calendar stage reached on any branch | `:290-299` |

Derivations of each are on the page that owns the process.

## 8. Plant-model behaviours a calibrator should know

Each item is derived on the page named; the citations here are the decisive lines.

1. **NPP_pft is gross fixation.** It is evaluated before the hour's respiration is summed (`GrosubsMod.F90:253`; `PlantBalMod.F90:101`, `:503`), so it equals CAN_GPP_pft outside grazing hours; ECO_NPP_col is net (`f90src/Balances/RedistMod.F90:226`). See [`growth_and_allocation.md`](growth_and_allocation.md) section 12.
2. **Phenology gates photosynthesis.** A deciduous branch fixes no CO2 unless its leaf-out hours have reached VRNLI or its leaf-off hours are still below VRNXI (`StomatesMod.F90:115-117`, `:1031-1033`). See [`phenology.md`](phenology.md) section 9.
3. **Allocation is hard-coded by stage.** Partition fractions are constants of `CalcPartitionCoeff` (`PlantBranchMod.F90:624-687`); the DM* parameters are growth yields, not partition shares (`:384-390`).
4. **Leaf protein is the lesser of an N route and a P route.** `AMIN1(N growth*CNWL, P growth*CPWL)` (`PlantBranchMod.F90:3561-3562`); only the binding route has leverage on photosynthetic capacity.
5. **XRLA sets both leaf appearance and leaf turnover** once a branch passes 25 nodes (`PlantPhenolMod.F90:1105`; `PlantBranchMod.F90:3999`).
6. **LAI above 5 diverts leaf growth to stalk** (`PlantBranchMod.F90:733-739`).
7. **Drought leaf-off is at -2 MPa for all vascular embryophyte types** at cb243228 (`PlantPhenolMod.F90:39`), and a drought-deciduous PFT with IEBTYP outside 2-4 aborts the run (`PlantInfoMod.F90:491-500`).
8. **ZTYPI acts as a continuous temperature offset** although it is labelled a zone (`StartqMod.F90:451`; `PlantInfoMod.F90:1092-1105`).
9. **Several plant parameters are inert or partly inert:** RSRA (not read on the live path; [`roots_and_uptake.md`](roots_and_uptake.md)), XPPD and XDL for day-neutral PFTs and in `DevelopMainBranch` (`PlantPhenolMod.F90:1509-1510`; `PlantBranchMod.F90:2917`), PB beyond one branch for IBTYP not 0 (`PlantPhenolMod.F90:40`, `:339`), CNSTK in leaf and sheath N:C (`GrosubsMod.F90:449`, `:454`, `:463`, `:465`).
10. **The plant balance check aborts the run** on a C, N or P error every hour ([`roots_and_uptake.md`](roots_and_uptake.md) section 13).
