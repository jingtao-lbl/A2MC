---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/APIs/` (13 files), callers in `drivers/ecosim/EcoSIMAPI.F90` and `f90src/Modelforc/Hour1Mod.F90`
**Last verified:** 2026-10-15
---

# API Layer: `f90src/APIs/`

The API layer copies data between the grid-indexed state of `f90src/Ecosim_datatype/` and the per-column containers the plant, microbial and solute kernels work on, and calls those kernels. It is built as the `APIs` library from 13 sources (`f90src/APIs/CMakeLists.txt:1-15`) and may include every lower layer: `Ecosim_datatype`, `APIData`, `Plant_bgc`, both microbial model directories, `HydroTherm`, `Disturbances`, `Balances`, transport and geochemistry (`:20-40`).

| File | Lines | Public routines | Role |
|---|---|---|---|
| `PlantMod.F90` | 142 | `PlantModel` (`:37`), `PlantCanopyRadsModel` (`:127`) | hourly plant driver; canopy-radiation driver |
| `PlantAPI.F90` | 104 | `PlantAPISend` (`:70`), `PlantAPIRecv` (`:40`) | ordered dispatch to the six transfer modules |
| `PlantColumnTransferMod.F90` | 395 | `SendPlantColumnInputs` (`:154`), `SendPlantColumnState` (`:296`), `ReceivePlantColumns` (`:53`) | column-level forcing and accumulators |
| `PlantStateTransferMod.F90` | 450 | `SendPlantState` (`:269`), `ReceivePlantState` (`:52`) | per-PFT state, fluxes and biomass |
| `PlantCanopyTransferMod.F90` | 375 | `SendPlantCanopy` (`:236`), `ReceivePlantCanopy` (`:49`) | per-PFT canopy, branch and node arrays |
| `PlantRootTransferMod.F90` | 259 | `SendPlantRoots` (`:179`), `ReceivePlantRoots` (`:48`) | per-PFT root layer arrays |
| `PlantRootAxisTransferMod.F90` | 193 | `SendPlantRootAxes` (`:132`), `ReceivePlantRootAxes` (`:46`) | per-root-axis arrays |
| `PlantTraitsTransferMod.F90` | 205 | `SendPlantTraits` (`:50`) | per-PFT traits, one way only |
| `PlantCanAPI.F90` | 271 | `PlantAPICanMSend` (`:55`), `PlantAPICanMRecv` (`:197`) | subset for canopy radiation |
| `PlantAPI4Uptake.F90` | 285 | `PlantUptakeAPISend` (`:55`), `PlantUPtakeAPIRecv` (`:234`) | subset for prescribed-phenology mode |
| `MicBGCAPI.F90` | 696 | `MicAPI_Init` (`:60`), `MicAPI_cleanup` (`:72`), `MicrobeModel` (`:84`) | per-layer microbial send, kernel, receive |
| `GeochemAPI.F90` | 371 | `soluteModel` (`:23`) | per-layer solute equilibrium send, kernel, receive |
| `SurfPhysAPI.F90` | 13 | none | empty module |

## 1. Who calls what, and when

| Entry | Called from | Gate | Cadence |
|---|---|---|---|
| `PlantCanopyRadsModel` | `hour1` (`f90src/Modelforc/Hour1Mod.F90:201`); ATS driver (`f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:296`) | none in `hour1` | hourly, per column, before the plant step |
| `MicrobeModel` | `Run_EcoSIM_one_step` (`drivers/ecosim/EcoSIMAPI.F90:63`) | `microbial_model` (`:61`) | hourly |
| `PlantModel` | `Run_EcoSIM_one_step` (`drivers/ecosim/EcoSIMAPI.F90:73`); ATS driver in prescribed-phenology mode (`f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:343`) | `plant_model .and. .not.ldo_radiation_test` (`drivers/ecosim/EcoSIMAPI.F90:71`) | hourly, after the microbes |
| `soluteModel` | `Run_EcoSIM_one_step` (`drivers/ecosim/EcoSIMAPI.F90:82`) | `soichem_model` (`:80`) | hourly, after the plants |
| `MicAPI_Init`, `MicAPI_cleanup` | `f90src/Main/InitEcoSIM.F90:57`, `f90src/Main/EcoSIMDesctruct.F90:59` | none | once |

All three kernels run every hour in a standard run. The order inside the hour is weather, `HOUR1` (including canopy radiation), water and heat (`WATSUB`), microbes, plants, solute chemistry, transport, erosion, redistribution, balance check (`drivers/ecosim/EcoSIMAPI.F90:49-124`).

## 2. `PlantMod.F90`

`PlantModel(yearIJ,NHW,NHE,NVN,NVS)` (`f90src/APIs/PlantMod.F90:37-107`):

| Step | Call | Line |
|---|---|---|
| landscape grazing set-up (full model only) | `PrepLandscapeGrazing`; copy landscape element store into `plt_site` | `:53-54` |
| per column, prescribed phenology (`ldo_sp_mode`) | `PlantUptakeAPISend` → `ROOTUPTAKES` → `extracts` → `PlantUPtakeAPIRecv` | `:60-68` |
| per column, full model | `PlantAPISend` | `:71` |
| | `EnterPlantBalance` (start of the plant mass-balance bracket; zeroes hourly flux sums through `ZeroGrosub`) | `:73` |
| | at hour 1, `SeedDeposition` | `:75-79` |
| | `PhenologyUpdate` | `:82` |
| | `ROOTUPTAKES` | `:85` |
| | `GROWPLANTS` | `:88` |
| | `EXTRACTs` | `:91` |
| | `ReSeedPlants` | `:93` |
| | `ExitPlantBalance` | `:95` |
| | `PlantAPIRecv` | `:97` |
| after the column loop | copy the landscape element store back | `:104` |

`PlantCanopyRadsModel(I,J,NY,NX,DepthSurfWatIce)` (`f90src/APIs/PlantMod.F90:127-140`) is `PlantAPICanMSend` → `CanopyConditionModel` → `PlantAPICanMRecv` (`:134-138`); the kernel is in `f90src/Plant_bgc/SurfaceRadiationMod.F90:49`.

## 3. `PlantAPI.F90`: ordered dispatch

`PlantAPI.F90` was 1527 lines at 2dea74d9 with all copies inline; it now only orders the calls, keeping each call inside its original PFT loop so accumulations happen in the same order (comment at `f90src/APIs/PlantAPI.F90:2-3`).

`PlantAPISend(yearIJ,NY,NX)` (`f90src/APIs/PlantAPI.F90:70-102`):

1. `SendPlantColumnInputs(I,NY,NX,I1)` (`:82`)
2. for every PFT slot `NZ = 1..NP0_col`: `SendPlantTraits(NY,NX,NZ)` (`:83-85`)
3. `SendPlantColumnState(I1,NY,NX)` (`:87`)
4. for every PFT slot: `SendPlantState`, `SendPlantCanopy`, `SendPlantRoots`, `SendPlantRootAxes` (`:88-93`)
5. layer copies of `REcoUptkSoilO2M_vr` and `FracAirFilledSoilPoreM_vr` into `plt_rbgc` and `plt_soilchem` (`:95-100`)

`PlantAPIRecv(I,J,NY,NX)` (`f90src/APIs/PlantAPI.F90:40-65`):

1. `ReceivePlantColumns(I1,NY,NX)` with `I1` the next day (`:50-51`)
2. for every PFT slot: `ReceivePlantState`, `ReceivePlantCanopy`, `ReceivePlantRoots`, `ReceivePlantRootAxes` (`:52-57`)
3. sums of root autotrophic respiration, root CO2 release and root O2 sink over layers `NUI_col..NK_col` into column totals (`:58-63`)

### 3.1 Consequences for parameters

- **Traits are pushed every hour and never pulled back.** `SendPlantTraits` copies every per-PFT trait into the `plt_*` containers on each call of `PlantAPISend`, and there is no `ReceivePlantTraits`. A kernel that modifies a trait inside `plt_*` (for example `UpdateRootProperty` in prescribed-phenology ATS mode, `f90src/Plant_bgc/UptakesMod.F90:485-488`) changes it for the current hour only.
- **Only derived values reach the kernel for some traits.** `SendPlantTraits` sends `RootSingleVesselRstaxial_pft` (`f90src/APIs/PlantTraitsTransferMod.F90:112`), computed in STARTQ from ARSRA and RVSR; `AlphaVesselAxialResist_pft` and `RootVesselRadius_pft` themselves are not sent. Examples of directly sent traits: `PlantInitThermoAdaptZone_pft` (`:70`), `VmaxSpecRubCarboxyRef_pft` (`:74`), `LeafProtein2Chl_pft` (`:83`), `SLA1_pft` (`:95`), `VmaxNH4Root_pft` for every root type (`:121`), `ShootRootNonstElmConduts_pft` (`:132`), `RootBiomGrosYld_pft` (`:146`), `rNCRoot_pft` (`:157`), `HourReq4LeafOut_brch` per branch (`:191`).
- **Fluxes come back as accumulators.** `ReceivePlantState` adds the hour's gross fixation into the column year-to-date GPP, `Eco_GPP_CumYr_col = Eco_GPP_CumYr_col + AZERO(plt_bgcr%GrossCO2Fix_pft(NZ))` (`f90src/APIs/PlantStateTransferMod.F90:58`), and copies `GrossCO2Fix_pft` (`:123`), `NetPrimProduct_pft` (`:243`), `ShootElms_pft` (`:84`), `RootElms_pft` (`:67`), `LeafStrutElms_pft` (`:85`), `CanopyLeafArea_pft` (`:94`) back to the grid arrays. `ReceivePlantColumns` copies the kernel's running `Eco_AutoR_CumYr_col` back (`f90src/APIs/PlantColumnTransferMod.F90:64`); `SendPlantColumnState` sent it in (`:328`).

### 3.2 Transfer modules

Each transfer module starts with the comment "Ordered ... transfers used by PlantAPISend/PlantAPIRecv" and is a long list of assignments.

| Module | References to `plt_*` | Send | Receive |
|---|---|---|---|
| `PlantColumnTransferMod` | 240 | `SendPlantColumnInputs` (`f90src/APIs/PlantColumnTransferMod.F90:154-294`): grid indices, thresholds, latitude, atmosphere, `lreset_laimax_pft` flags (`:162-175`); `SendPlantColumnState` (`:296-394`) | `ReceivePlantColumns` (`:53-152`) |
| `PlantStateTransferMod` | 380 | `SendPlantState` (`f90src/APIs/PlantStateTransferMod.F90:269-449`) | `ReceivePlantState` (`:52-267`) |
| `PlantCanopyTransferMod` | 216 | `SendPlantCanopy` (`f90src/APIs/PlantCanopyTransferMod.F90:236-374`) | `ReceivePlantCanopy` (`:49-234`) |
| `PlantRootTransferMod` | 175 | `SendPlantRoots` (`f90src/APIs/PlantRootTransferMod.F90:179-258`) | `ReceivePlantRoots` (`:48-177`) |
| `PlantRootAxisTransferMod` | 82 | `SendPlantRootAxes` (`f90src/APIs/PlantRootAxisTransferMod.F90:132-192`) | `ReceivePlantRootAxes` (`:46-130`) |
| `PlantTraitsTransferMod` | 138 | `SendPlantTraits` (`f90src/APIs/PlantTraitsTransferMod.F90:50-204`) | none |

## 4. `PlantCanAPI.F90`

`PlantAPICanMSend(NY,NX)` (`f90src/APIs/PlantCanAPI.F90:55-193`) sends only what `CanopyConditionModel` needs (canopy leaf and stem areas, heights, optics, sky and atmosphere state); `PlantAPICanMRecv` (`:197-269`) returns the canopy radiation state. It runs from `hour1`, before `PlantModel`, so the plant step sees this hour's absorbed radiation.

## 5. `PlantAPI4Uptake.F90`: prescribed phenology

Used when `ldo_sp_mode` is true (`f90src/APIs/PlantMod.F90:60`), which also switches microbes and chemistry off (`drivers/ecosim/EcoSIMAPI.F90:307-312`). `PlantUptakeAPISend` (`f90src/APIs/PlantAPI4Uptake.F90:55-231`) sends leaf and stalk area, canopy height and leaf area as prescribed inputs (`:66`, `:81`, `:144-147`) and sets the rooting depth to the column maximum, `plt_morph%MaxSoilLays4Root_pft(NZ) = NK_col(NY,NX)` (`:148`). In the full model the same variable is the state value updated by phenology (`f90src/Plant_bgc/PlantPhenolMod.F90:453`, `StagePlantPhenology`) and by root growth (`f90src/Plant_bgc/RootMod.F90:5459`, `GetInLayerRootDepth`), copied in by `SendPlantState` (`f90src/APIs/PlantStateTransferMod.F90:391`). `PlantUPtakeAPIRecv` (`f90src/APIs/PlantAPI4Uptake.F90:234-283`) returns uptake-related fields only.

## 6. `MicBGCAPI.F90`: microbial kernel, per layer

Module-level containers: `micfor` (forcing), `micstt` (state), `micflx` (fluxes) and `nmicdiag` (`f90src/APIs/MicBGCAPI.F90:45-48`), initialised in `MicAPI_Init` (`:60-70`).

`MicrobeModel(I,J,NHW,NHE,NVN,NVS)` (`f90src/APIs/MicBGCAPI.F90:84-176`), per column:

1. incident PAR at the litter surface from `RadPAR2LitR_col + RadPAR2Soil_col`, per unit area;
2. for every layer `L = 0..NL_col` with pore volume and (for `L > 0`) at or below the surface layer, `MicBGC1Layer(I,J,L,NY,NX,PAR)` with organic-matter sums before and after;
3. PAR attenuation to the next layer by litter or soil extinction plus cyanobacterial self-shading, `exp(-tau)` with `tau = k*DLYR + k_cyanoC*cyanobacterial C/area` (litter `k_litr = 250 m-1`, soil from `CalcKSoilPAR`);
4. layers without pore volume get zero microbial uptake, release and N2 fixation;
5. after the layer loop, `DownwardMixOM` for every layer and `SOMRemovalByDisturbance`.

`MicBGC1Layer` (`:180-195`) sets `micfor%L` and `micfor%PAR_rad` (`:187`), then `MicAPISend` (`:198-489`) → `SoilBGCOneLayer` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:74`) → `MicAPIRecv` (`f90src/APIs/MicBGCAPI.F90:491-690`). `MicAPISend` flags the litter layer with `micfor%litrm=(L==0)` (`:221`). The microbial parameters (`OMGR`, `RMOM`, `SPOMC`, ...) are not passed through this layer: the kernel modules `use NitroPars` and `MicBGCPars` directly (for example `f90src/Microbial_bgc/Box_Micmodel/AerobicBacteriaMod.F90:11`).

## 7. `GeochemAPI.F90`: solute equilibria, per layer

`soluteModel(I,J,...)` (`f90src/APIs/GeochemAPI.F90:23-150`) zeroes a local `chem_var_type` and `solute_flx_type` (`:36-37`), then for each column and each layer with pore volume and water (`:98`) and soil mass (`:114`) calls `GeochemAPISend` (`:134`), `GeoChemEquilibria` (`:136`; kernel at `f90src/Geochem/Layers_chem/SoluteMod.F90:43`), `GeochemAPIRecv` (`f90src/APIs/GeochemAPI.F90:138`) and `UpdateFertilizerBand` (`:140`); after the layers, `UpdateSurfResidueSolute` (`:146`). `GeochemAPISend` (`:154-256`) and `GeochemAPIRecv` (`:260-369`) add the salt tracers when `salt_model` is on (`:166`, `:298`).

## 8. `SurfPhysAPI.F90`

An empty module (13 lines) with no public routines. Surface energy and water physics still use the `Ecosim_datatype` arrays directly.

## 9. Patterns

| Pattern | Modules | Granularity |
|---|---|---|
| column send, kernel sequence, column receive | `PlantAPI` with the six transfer modules | once per column per hour, PFT loops inside |
| reduced column send and receive | `PlantCanAPI`, `PlantAPI4Uptake` | once per column per hour |
| per-layer send, kernel, receive with module-level containers passed as arguments | `MicBGCAPI`, `GeochemAPI` | once per soil layer per hour |
| driver only | `PlantMod` | orchestration |

## 10. Following two parameters from file to kernel

**VCMX** (C3 rubisco carboxylation capacity):

1. `ReadPlantTraitTable` reads the whole column into `VmaxRubCarboxyRef_tab` (`f90src/IOutils/PlantInfoMod.F90:1736`).
2. Each year `SetPlantTraits` copies record `loc` into `VmaxSpecRubCarboxyRef_pft` (`:731`) and `ReadPlantProperties` multiplies it by 1.92 (`:507`).
3. Each hour `SendPlantTraits` copies it into `plt_photo%VmaxSpecRubCarboxyRef_pft` (`f90src/APIs/PlantTraitsTransferMod.F90:74`).
4. The kernel uses it in `C3Photosynthesis` (`f90src/Plant_bgc/StomatesMod.F90:441`) and, in `PhotosynsDiag`, in both the C4 bundle-sheath branch (`:134`) and the C3 branch (`:148`).

**ARSRA** (axial resistance corrector):

1. Read into `AlphaVesselAxialResist_tab` (`f90src/IOutils/PlantInfoMod.F90:1797`), copied to `AlphaVesselAxialResist_pft` each year (`:794`).
2. Used only in STARTQ, first simulated year: `RootSingleVesselRstAxial_pft = AlphaVesselAxialResist_pft*Rax_ref*(1.e-6/RootVesselRadius_pft)**4` (`f90src/Ecosim_mods/StartqMod.F90:580`).
3. Each hour `SendPlantTraits` sends the derived `RootSingleVesselRstaxial_pft` (`f90src/APIs/PlantTraitsTransferMod.F90:112`), which `CalcPlantHydroResistance` uses for primary and medium root axial resistance (`f90src/Plant_bgc/UptakesMod.F90:1310`, `:1312`).

## 11. Changes since 2dea74d9

- `PlantAPI.F90` split into a 104-line dispatcher and six transfer modules (this page §3).
- `MicrobeModel` now carries PAR down the profile for cyanobacteria (`f90src/APIs/MicBGCAPI.F90:84-176`).
- `PlantModel` now calls `SeedDeposition` at hour 1 (`f90src/APIs/PlantMod.F90:75-79`).
- Unchanged: `MicrobeModel` and `soluteModel` are called every hour from the driver at both pins (`drivers/ecosim/EcoSIMAPI.F90:63`, `:82` here); the 2dea74d9 wiki's statement that they had no caller was wrong.
