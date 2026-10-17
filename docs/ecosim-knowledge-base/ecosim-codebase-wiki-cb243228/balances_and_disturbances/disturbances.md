---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/Disturbances/`, the plant-side disturbance modules `f90src/Plant_bgc/PlantDisturb*Mod.F90`, the management readers in `f90src/IOutils/{PlantInfoMod,ReadManagementMod}.F90`, and tillage mixing in `f90src/Balances/TillageMixMod.F90`
**Last verified:** 2026-10-15
---

# Disturbances: harvest and cutting, fire, tillage, fertiliser, warming, erosion

Management enters EcoSIM from two NetCDF files named in the runfile: the plant-management file `pft_mgmt_in` (planting, harvest, cutting, grazing, plant fire) and the soil-management file `soil_mgmt_in` (tillage, fertiliser, irrigation, soil fire). The plant-side events execute inside `PlantModel`; the soil-side events in `HOUR1`, `MicrobeModel`, `REDIST` and `DAY`. Most events fire once, at the hour of solar noon.

## 1. Where each disturbance runs in the hour

| disturbance | trigger | runs in | entry routine |
|---|---|---|---|
| harvest, cutting, thinning, pruning | management day, `J == INT(SolarNoonHour_col)` | `PlantModel` → `GrowPlants` (`f90src/Plant_bgc/GrosubsMod.F90:106`) | `RemoveBiomassByDisturbance` (`f90src/Plant_bgc/PlantDisturbsMod.F90:297-340`) |
| grazing, herbivory | every hour of the management days | same | same, through `PlantDisturbByGrazingMod`; landscape staging `PrepLandscapeGrazing` (`f90src/Disturbances/PlantDisturbMod.F90:35`, called `f90src/APIs/PlantMod.F90:53`) |
| plant fire (`iHarvstType_pft = 5`) | fire year, noon | same | `PlantDisturbByFireMod` |
| tillage effect on plants | tillage code 1-20, noon | same | `RemoveBiomByTillage` (`f90src/Plant_bgc/PlantDisturbByTillageMod.F90:272-357`) |
| soil fire, litter removal (codes 22, 21) | noon | `MicrobeModel` (`f90src/APIs/MicBGCAPI.F90:169`) | `SOMRemovalByDisturbance` (`f90src/Disturbances/SoilDisturbMod.F90:40`) |
| tillage mixing (codes 1-20) | noon | `REDIST` → `UpdateOutputVars` (`f90src/Balances/RedistMod.F90:252`) | `ApplyTillageMixing` (`f90src/Balances/TillageMixMod.F90:36`) |
| fertiliser, manure, inhibitors | noon | `HOUR1` (`f90src/Modelforc/Hour1Mod.F90:247`) | `ApplyFertilizerAtNoon` (`f90src/Disturbances/FertilizerMod.F90:35-64`) |
| automatic irrigation | daily | `DAY` (`f90src/Modelforc/DayMod.F90:83`) | `TillageandIrrigationEvents` (`:219`) |
| bio-aerosol deposition | daily, hour 12 | `DAY` (`DayMod.F90:77`) | `ApplyBioAerosol` (`f90src/Modelforc/DepositionMod.F90`) |
| warming (cable / IR / open-top chamber) | warming window | `WATSUB` (`f90src/HydroTherm/SoilPhys/WatsubMod.F90:118-122`), `PrepHourlyWeather` (`f90src/Modelforc/WthrMod.F90:103-106`) | `EcosysWarmingMod` |
| erosion | every hour if `iErosionMode` is 1 or 3 | `EROSION` (`drivers/ecosim/EcoSIMAPI.F90:110`) | `erosion` (`f90src/Disturbances/ErosionMod.F90:62-90`) |

## 2. Harvest and cutting

### 2.1 The management record

Each PFT carries up to 24 management strings per year. `ReadPlantMgmtinfo` (`f90src/IOutils/PlantInfoMod.F90:243-383`) reads the date `DDMMYYYY` (`:305`) and then the comma-separated record `DY,ICUT,JCUT,HCUT,PCUT,ECUT11,ECUT12,ECUT13,ECUT14,ECUT21,ECUT22,ECUT23,ECUT24` (`:307-308`; example in the comment `:309`), and stores it on the ordinal day `IDY`:

| field | stored as | line | meaning (comment `:324-331`, codes `f90src/Modelconfig/ElmIDMod.F90:106-116`) |
|---|---|---|---|
| `ICUT` | `iHarvstType_pft(NZ,IDY)` | `:332` | 0 none, 1 grain, 2 all above ground, 3 pruning, 4 grazing, 5 fire, 6 herbivory |
| `JCUT` | `jHarvstType_pft(NZ,IDY)` | `:333` | 0 no action, 1 terminate the PFT, 2 terminate and reseed; `JCUT=1` also sets the harvest day and year (`:319-323`) |
| `HCUT` | `CanopyCutProxy_pft(NZ,IDY)` | `:334` | types 0-2: cutting height (m) if > 0, fraction of LAI removed if < 0; type 3: clumping-factor multiplier; types 4/6: animal or insect biomass |
| `PCUT` | `THIN_pft(NZ,IDY)` | `:335` | types 0-3, 5: fraction of the population removed; types 4/6: specific herbivory rate |
| `ECUT11..ECUT14` | `FracBiomHarvsted(iHarvst_pft, leaf / fine non-leaf / stalk / standing dead)` | `:339-342` | fraction of each organ group removed from the PFT |
| `ECUT21..ECUT24` | `FracBiomHarvsted(iHarvst_col, same order)` | `:346-349` | fraction of the removed material that leaves the ecosystem; the rest becomes litter |

For grazing and herbivory the record is copied to every day between two successive entries (`:351-374`). A near-identical parser exists for fire-year management (`ReadPlantFireMgmt`, `f90src/IOutils/ReadManagementMod.F90:603-685`, lines `:639-680`). Annual deciduous crops also get an automatic grain harvest with terminate-and-reseed set inside `ResetBranchPhenology` (`f90src/Plant_bgc/PlantBranchMod.F90:2704-2717`): `ECUT1x = 1`, `ECUT21 = 0`, `ECUT22 = 1`, `ECUT23 = ECUT24 = 0`, `THIN = 0`.

### 2.2 Execution order (`RemoveBiomassByDisturbance`, `PlantDisturbsMod.F90:297-340`)

1. `StageDisturbances` zeroes the removal and litter accumulators (`:66-87`).
2. `RemoveDeadAnnual` (`:116-219`): a drought-deciduous annual that has stalled for `Days2CallFalseBreak` days dies; shoot and roots (layers `NU..MaxNumRootLays`) go to fine litter.
3. `RemoveBiomByMgmt` (`:89-113`) → `RemoveBiomByHarvest` (`:744-984`) and `RemoveBiomByTillage`.
4. If `iHarvstType_pft >= 0`: `RemoveStandingDead` (`:245-294`), `PlantShootDisturbance` (`:343-382`: `ApplyDisturbanceBiomRemoval`, `AbvgBiomRemovalByDisturb`, `LiterfallByDisturbance`), then the `ZERO4*` thresholds are recomputed from the new population (`:333-335`).

`RemoveBiomByHarvest` acts at solar noon for types 0-3 and 5, and every hour for grazing and herbivory (`:814-816`).

### 2.3 What is cut

- **Population** (types other than 4/6): `PPX`, `PlantPopuLive_pft` and `PlantPopuDead_pft` are multiplied by `1 - THIN` (`:837-840`); with terminate-and-reseed they are reset to the seeding density instead (`:842-849`).
- **Pruning** (type 3): `ClumpFactor_pft *= HCUT` (`:851-853`).
- **LAI-fraction cut** (types 0-2 with `HCUT < 0`): the cut height is found by removing `abs(HCUT)` of canopy leaf area from the top canopy layer down (`:856-877`).
- **Leaves**, per canopy layer, in `HarvestCanopy` (`:1658` onward): the fraction of the layer below the cut height, `FracHeightLeft` (`:1709-1714`; 0 under pruning, `:1716`), gives the retained fraction `FrcLeafMassLeft = 1 - (1 - FracHeightLeft)*ECUT11` when `THIN = 0` (`:1719-1721`), or `1 - THIN` otherwise (`:1723`).
- **Stalk**, per branch, in `CutBranchStalk` (`:1071` onward): `FracHeightLeft = min(1, HCUT/BranchLength)` (`:1122`) and `FractionStalkMassLeft = 1 - (1 - FracHeightLeft)*ECUT13` when `THIN = 0` (`:1127-1130`).
- **Grain and husks**: `FracGrainNotHvsted = 1 - ECUT12` (`:1315`); petioles and sheaths at cut nodes use `ECUT12` (`:1885`, `:1890`).
- **Standing dead**: retained fraction `1 - ECUT14` when `THIN = 0` (`:268`), `1 - THIN` otherwise (`:271`).

Every organ uses the same bookkeeping. With retained fraction `Left` and a second fraction `FHVSH` (`FHVSH = Left` except under thinning with harvest type 0, where `FHVSH = 1 - (1 - FracHeightLeft)*ECUT1x*THIN`, for example `:273`, `:1134`, `:1725`), the organ mass `M` is split into kept `Left*M`, **removed** `(1 - FHVSH)*M` and **killed to litter** `(FHVSH - Left)*M` (standing dead `:287-289`; stalk `:1162-1163`; leaves `:1783-1792`).

### 2.4 Where the removed material goes

`ApplyDisturbanceBiomRemoval` (`:640-741`) splits the removed part with the ecosystem fractions: for harvest types 0, 2 and 3 each group sends `Removal*(1 - ECUT2x)` to litter (`:669-716`); for grain harvest (type 1) everything removed goes to litter except `GrainHarvst*ECUT22` (`:685-692`). Grazing and fire call their own routines (`:718-737`). Then `AbvgBiomRemovalByDisturb` (`:496-637`) forms

```
TotalAbgElmntRemoval = CanopyNonst + Leaf + PetoleSheth + Woody + Standead removals     (:547)
TotalAbgElmnt2Litr   = CanopyNonst + Leaf + FineNonleaf + Woody + Standead to-litter     (:548)
export               = TotalAbgElmntRemoval - TotalAbgElmnt2Litr
```

and books the export as `PlantElmDistLoss_pft += export` (`:564-568`; this is the plant-balance outflow), `EcoHavstElmnt_CumYr_pft` and `EcoHavstElmnt_CumYr_col += export` (`:626-629`) and `Eco_NBP_CumYr_col -= export(C)` (`:630`). With terminate-and-reseed (`JCUT = 2`) the export is returned to the PFT's seasonal storage instead (`:599-604`); if the live population has reached zero, seasonal storage is booked as disturbance loss and the root system reset (`:608-624`).

`LiterfallByDisturbance` (`:385-493`) places the to-litter parts, all on the surface layer `L = 0`: nonstructural, leaf and fine non-leaf material into the fine-litter complex (`:443-446`). Stalk and standing-dead material goes to fine litter for non-woody plants or turnover pattern 0 (`:448-450`); for woody vascular plants the thinning-killed woody and standing-dead parts become standing dead again (`:452-453`) and the rest is split between woody and fine litter by `FracWoodStalkElmAlloc2Litr` (`:455-461`).

### 2.5 Roots and storage at harvest

For every type except grazing, herbivory and all-above-ground (`:930-931`), primary-axis root mass is scaled by `1 - THIN` (`:933-938`) and each layer `L = NU..MaxNumRootLays` loses the fraction `THIN` to litter (`RootRemovalLbyFire`, `f90src/Plant_bgc/PlantDisturbByFireMod.F90:440-448`, then `HarvstUpdateRootStateL`, `PlantDisturbsMod.F90:941-951`); layer `NK = MaxNumRootLays + 1` is not visited. Perennials also send `THIN` of seasonal storage to litter at the planting-depth layer (`:961-977`).

### 2.6 Standing dead afterwards

Standing dead decays to surface litter every hour in `Live2DeadTransformation`: `XFRE = Kd*fTCanopyGroth_pft*StandDeadCompKElms_pft` with `Kd = 1.5814e-4` h-1 for non-woody plants and `1.5814e-5` h-1 otherwise (`f90src/Plant_bgc/GrosubsMod.F90:131-132`, `:181-185`, `:206-217`), into fine litter (non-woody) or woody litter (woody).

### 2.7 Outputs

| tape variable | source | line |
|---|---|---|
| `HVST_C_FLX_pft` | `EcoHavstElmnt_CumYr_pft/area`, a within-year cumulative despite the registered unit `gC/m2/hr` | `f90src/IOutils/HistData/HistUpdatePlant.F90:86`; `HistRegisterPlant.F90:381` |
| `ECO_HVST_C_col` | `EcoHavstElmnt_CumYr_col/area` | `HistUpdateColumn.F90:199` |
| `STANDING_DEAD_C_pft` | `StandDeadStrutElms_pft/area` | `HistUpdatePlant.F90:113` |
| `SURF_LITRf_C_FLX_pft` | `SurfLitrfalStrutElms_CumYr_pft/area` | `HistUpdatePlant.F90:85` |

## 3. Fire

**Configuration.** `FireEvents` in `/ecosim/` lists `YYYY/entry;YYYY/entry` (`config_fire`, `f90src/Disturbances/FireMod.F90:24-98`); the parser returns silently unless character 5 is `/` (`:39`), although the header comment shows `:` (`:27`). Fire requires `soil_mgmt_in` (`:91-92`). Each year `check_fire` (`:100-116`) advances through the list, and `ReadClimSoilForcing` calls `ReadFire` in a fire year (`f90src/IOutils/readsmod.F90:235-237`). The entry is `plantvar,soilvar` (`ReadManagementMod.F90:548`): the soil part is read as a tillage-style record (`:560-568`) that sets `iSoilDisturbType_col = 22`, the plant part through `ReadPlantFireMgmt` (`:586-595`).

**Soil fire** (`SOMRemovalByDisturbance`, `SoilDisturbMod.F90:40`): at noon for codes 21 (litter removal) and 22 (fire) (`:72-73`). Fire burns from the litter layer down to the first layer that is too wet or too poor in organic C (`:81-92`); the wetness limit `VolMaxSoilMoist4Fire` is 1.0 (`f90src/Utils/EcoSimConst.F90:40`), so only the organic-C test (`CSoilOrgM <= FORGC = 1e5`) stops it. Each burned layer loses the fraction `DCORPC = min(0.999, DepzCorp)*(CSOC - FORGCX)/(max(CSOC, orgcden) - FORGCX)` (`:106-107`); litter removal uses `min(0.999, DepzCorp)` on layer 0 only (`:94`, `:109`). Of the N and P removed with that C, the fractions `EFIRE(1:2, code)` = (1.0, 1.0) for code 21 and (0.917, 0.167) for code 22 (`f90src/Modelpars/NitroPars.F90:121`, `:264`) leave with it; the rest stays in the layer as organic N and P, in the lignin component of litter complexes and the protein component otherwise (`SoilDisturbMod.F90:133-142`). `Eco_NBP_CumYr_col` is debited (`SoilDisturbMod.F90:369`, `:384`).

**Plant fire** (`iHarvstType_pft = 5`) is handled by `f90src/Plant_bgc/PlantDisturbByFireMod.F90`: `ShootBiomRemovalByFire` (called `PlantDisturbsMod.F90:730`), `AbvgBiomRemovalByFire` (`:583`) and root burning `RootRemovalLbyFire` (`:944`), with plant emission factors `EFIRE = (0.917, 0.167)` for N and P (`PlantDisturbByFireMod.F90:28`, `:35`). `AbvgBiomRemovalByDisturb` skips its own `PlantElmDistLoss_pft` booking for fire (`:564`) because the fire module books the burned mass into both `FireLossE_pft` and `PlantElmDistLoss_pft` (`PlantDisturbByFireMod.F90:122-123`, `:313-314`).

## 4. Tillage

The soil-management tillage code `iSoilDisturbType_col` (1-20 tillage, 21 litter removal, 22 fire, 23-24 drainage) sets the daily mixing fraction in `TillageandIrrigationEvents`: `CORP = code/10` for codes up to 10, `(code-10)/10` for 11-20, and `XTillCorp_col = 1 - CORP` (`f90src/Modelforc/DayMod.F90:239-248`). Soil mixing happens at noon in `ApplyTillageMixing` when `XTillCorp_col < 1` and the tillage depth `DepzCorp_col > 0` (`f90src/Balances/TillageMixMod.F90:61-62`; see [mass_balance.md](mass_balance.md) §7). Plants are hit at noon by `RemoveBiomByTillage` for non-woody PFTs only (`PlantDisturbByTillageMod.F90:319-323`), after the planting day; codes 11-20 spare PFT 1 (`:325`): population is scaled by `XTillCorp` and shoots and roots are sent to litter (`:327-336`); a PFT whose population reaches zero is terminated (`:338-350`).

## 5. Fertiliser, manure and inhibitors

`ApplyFertilizerAtNoon` (`f90src/Disturbances/FertilizerMod.F90:35-64`) runs at noon and calls, in order, `ApplyMineralFertilizer` (`:417`), `ApplyManure` (`:121`) and `ApplyUreaNitrifierInhibitor` (`:67`). Mineral N (NH4, NH3, urea, NO3, broadcast and banded), P (monocalcium phosphate, apatite, PO4) and Ca (lime, gypsum) come from `FERT(code,I)` (`:459-483`). Broadcast fertiliser with application depth `<= 0` goes to the surface layer `LFDPTH = 0` in the fraction `1 - exp(-0.008*litterC/area)` and to the top soil layer for the rest; a band or deep application goes to the layer at the application depth (`:500-515`). Plant residue and manure C, N, P (`:487-493`) are placed at the application layer with residue-type-specific protein, carbohydrate, cellulose and lignin fractions (for example maize 0.080, 0.245, 0.613, 0.062, `:173-177`), and the applied organic C is added to `Eco_NBP_CumYr_col` when the manure-type code `IYTYP(iAmendtyp_Manure)` is below 3 (`:405-409`). Urea switches on the urea-hydrolysis inhibitor activity at the application layer, with the inhibitor type set by `IYTYP` (`:81-104`); `IYTYP` 3 or 4 switches on the nitrification inhibitor (`:106-117`).

## 6. Soil warming

`warming_exp` is a `key[value];...` string (example `f90src/Disturbances/EcosysWarmingMod.F90:7`) parsed by `config_soil_warming` (`:198-290`): `type[ir_heating]`, `type[cable_heating]` or `type[open_top_chamber]` (codes 1, 2, 3, `:223-237`), or `types[...]` combining cable heating with IR (21) or OTC (23) (`:238-251`), plus `loc[NY,NX]` (`:257-264`). Cable heating is applied in `WATSUB` (`apply_soil_cable_warming`, `:539`, called `WatsubMod.F90:121`) against a reference soil-temperature history loaded for every warmed year (`check_warming_year`, `:171-179`; driver `drivers/ecosim/EcoSIMAPI.F90:453-457`); IR and OTC modify the forcing in `PrepHourlyWeather` (`apply_IR_warming` `:576`, `apply_OTC_warming` `:504`).

## 7. Erosion

`erosion` (`ErosionMod.F90:62-90`) runs only for `iErosionMode` 1 or 3 (`:75`): per sub-cycle `SedimentDetachmentM` (`:93`) and `SedimentTransportM` (`:258`), then `LateralXGridSedmentFlux` (`:399`) and, unless `column_mode`, `XBoundErosionFlux` (`:744`). Mass moves in `REDIST` (`SoilErosion`, `RedistMod.F90:561`) and layer edges move in `SoilLayerDynMod`.

## 8. Management fields: source map

The management surface is not indexed as calibration parameters; this table is for tracing.

| file field | Fortran variable | read at (routine) | used at (routine) | effect |
|---|---|---|---|---|
| `ICUT` | `iHarvstType_pft` | `PlantInfoMod.F90:332` (`ReadPlantMgmtinfo`) | `RemoveBiomByHarvest` `:814-816`; `ApplyDisturbanceBiomRemoval` `:674-737` | selects the harvest branch |
| `JCUT` | `jHarvstType_pft` | `:333` | `RemoveBiomByHarvest` `:837-849`; `AbvgBiomRemovalByDisturb` `:564`, `:599` | terminate or reseed |
| `HCUT` | `CanopyCutProxy_pft` | `:334` | `RemoveBiomByHarvest` `:852`, `:856-877`; `HarvestCanopy` `:1710`; `CutBranchStalk` `:1122` | cut height, LAI fraction or clumping multiplier |
| `PCUT` | `THIN_pft` | `:335` | `RemoveBiomByHarvest` `:838-840`, `:933`; `RemoveStandingDead` `:267-273`; `HarvestCanopy` `:1719-1725` | population fraction removed |
| `ECUT11..14` | `FracBiomHarvsted(iHarvst_pft,1:4)` | `:339-342` | `HarvestCanopy` `:1720`; `CutBranchStalk` `:1129`; grain `:1315`; `RemoveStandingDead` `:268` | fraction cut per organ group |
| `ECUT21..24` | `FracBiomHarvsted(iHarvst_col,1:4)` | `:346-349` | `ApplyDisturbanceBiomRemoval` `:669-672`, `:689` | fraction exported; the rest to litter |

## Calibration parameters

No plant-file or microbial-file calibration parameter is owned here. The fire factors `EFIRE` and the standing-dead decay constants are compile-time values.
