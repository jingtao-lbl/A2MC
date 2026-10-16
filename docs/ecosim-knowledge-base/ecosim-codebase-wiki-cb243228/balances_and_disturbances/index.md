---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/Balances/` (7 files), `f90src/Disturbances/` (6 files), and the plant-side disturbance modules they hand off to
**Last verified:** 2026-10-15
---

# Balances and disturbances

Two directories that are often confused. `f90src/Balances/` is end-of-hour state bookkeeping: it applies the fluxes the physics and biology computed (`redist`), moves sediment, mixes soil at tillage and re-layers the profile. `f90src/Disturbances/` holds the soil-side and forcing-side disturbance logic: fertiliser, soil fire, warming, erosion and grazing staging. Plant-side disturbance (harvest, cutting, thinning, plant fire, grazing removal, tillage damage) lives in `f90src/Plant_bgc/PlantDisturb*Mod.F90` and is documented here because it is driven by the same management inputs.

The conservation checks that can stop a run are not in `Balances/`; they live in `ModelDiags/BalancesMod.F90`, `WatsubMod`, the transport modules and `PlantBalMod`. All of them are listed in [mass_balance.md](mass_balance.md) §2.

## 1. Pages

| page | covers |
|---|---|
| [mass_balance.md](mass_balance.md) | every hourly balance check and what aborts; `redist` and its call order; NEE, NBP and heterotrophic-respiration accumulators; soil relayering; tillage mixing; sediment sinking |
| [disturbances.md](disturbances.md) | harvest and cutting from the plant-management record (`ICUT`, `JCUT`, `HCUT`, `PCUT`/`THIN`, `ECUT11-24`) and where cut biomass and standing dead go; soil and plant fire; tillage; fertiliser and inhibitors; warming; erosion |

## 2. Files in `f90src/Balances/`

| file | lines | main routines | role |
|---|---|---|---|
| `RedistMod.F90` | 1511 | `redist` (`:76`), `UpdateOutputVars` (`:160`), `ModifyExWTBLByDisturbance` (`:279`), `HandleSurfaceBoundary` (`:376`), `SoilErosion` (`:561`), `LitterLayerSummary` (`:669`), `UpdateTSoilVSMProfile` (`:776`), `UpdateChemInSoilLays` (`:896`), `AddFlux2SurfaceResidue` (`:1306`) | applies the hour's fluxes to state, assembles ecosystem C accumulators, calls tillage mixing |
| `SoilLayerDynMod.F90` | 2078 | `UpdateSoilGrids` (`:63`), `UpdateLayerEdges` (`:607`), `MoveSOM` (`:1456`), `MoveHeatWat` (`:2003`) | soil relayering by water level, freeze-thaw, erosion and SOM change; only active with `iErosionMode >= 0` |
| `TillageMixMod.F90` | 621 | `ApplyTillageMixing` (`:36`), `Mix1D..Mix4D` (`:381-596`), `DeriveTillageProf` (`:597`) | tillage mixing at solar noon |
| `LateralTranspMod.F90` | 435 | `XGridTranspt` (`:39`), `SumSedmentTranspFlux` (`:149`), `FlowXGrids` (`:372`) | sums directional fluxes into net cell changes |
| `ErosionBalMod.F90` | 238 | `SinkSediments` (`:28`), `ZeroErosionArray` (`:207`) | sediment sinking from ponds |
| `RunoffBalMod.F90` | 696 | `XGridBoundSolutesRunoff` (`:31`) and helpers | boundary solute losses; its call in `redist` is commented out (`RedistMod.F90:119`) |
| `RedistDataMod.F90` | 179 | `InitTflxType`, `DestructTflxType` | shared transport and redistribution arrays |

## 3. Files in `f90src/Disturbances/`

| file | lines | main routines | role |
|---|---|---|---|
| `FertilizerMod.F90` | 781 | `ApplyFertilizerAtNoon` (`:35`), `ApplyUreaNitrifierInhibitor` (`:67`), `ApplyManure` (`:121`), `ApplyMineralFertilizer` (`:417`) | mineral fertiliser, residue and manure, inhibitors |
| `SoilDisturbMod.F90` | 395 | `SOMRemovalByDisturbance` (`:40`) | soil fire (code 22) and litter removal (code 21) |
| `FireMod.F90` | 117 | `config_fire` (`:24`), `check_fire` (`:100`) | fire-year schedule from `FireEvents` |
| `EcosysWarmingMod.F90` | 638 | `config_soil_warming` (`:198`), `check_warming_dates` (`:130`), `check_warming_year` (`:171`), `apply_OTC_warming` (`:504`), `apply_soil_cable_warming` (`:539`), `apply_IR_warming` (`:576`) | warming experiments |
| `ErosionMod.F90` | 987 | `erosion` (`:62`), `SedimentDetachmentM` (`:93`), `SedimentTransportM` (`:258`), `LateralXGridSedmentFlux` (`:399`), `XBoundErosionFlux` (`:744`) | sediment detachment and transport |
| `PlantDisturbMod.F90` | 77 | `PrepLandscapeGrazing` (`:35`) | averages grazable shoot biomass over the landscape grazing unit before plant BGC |

## 4. Plant-side disturbance modules (in `f90src/Plant_bgc/`)

| file | lines | role |
|---|---|---|
| `PlantDisturbsMod.F90` | 2336 | `RemoveBiomassByDisturbance` (`:297`) and the harvest, cutting, thinning, standing-dead and litter routing ([disturbances.md](disturbances.md) §2) |
| `PlantDisturbByFireMod.F90` | 526 | plant fire: shoot, standing dead and root burning, emission factors `EFIRE` |
| `PlantDisturbByGrazingMod.F90` | 474 | grazing and herbivory removal |
| `PlantDisturbByTillageMod.F90` | 587 | `RemoveBiomByTillage` (`:272`) and the shoot and root losses at tillage |

## 5. Timing in one picture

```
DAY            tillage fraction XTillCorp_col = 1 - CORP; automatic irrigation; bio-aerosol at hour 12
HOUR1          ApplyFertilizerAtNoon                       (solar noon)
MicrobeModel   SOMRemovalByDisturbance: soil fire, litter removal   (solar noon)
PlantModel     PrepLandscapeGrazing (hourly);
               GrowPlants -> RemoveBiomassByDisturbance: harvest, cutting, thinning, plant fire,
               tillage damage (solar noon); grazing (hourly);
               Live2DeadTransformation: standing dead -> surface litter (hourly)
EROSION        sediment detachment and transport (hourly, iErosionMode 1 or 3)
REDIST         UpdateOutputVars -> ApplyTillageMixing     (solar noon); UpdateSoilGrids relayering
WATSUB / PrepHourlyWeather: cable / IR / OTC warming inside the warming window
```

## 6. Key facts to carry away

- A disturbance changes the plant balance only through `PlantElmDistLoss_pft` (exports) and litterfall; both enter `CheckPlantBalanceZ` (`f90src/Plant_bgc/PlantBalMod.F90:820-822`). The P check is skipped on planting and harvest days (`:937`); the C and N checks are not.
- Harvested exports reduce `Eco_NBP_CumYr_col` and accumulate in `EcoHavstElmnt_CumYr_*`, which feed `ECO_HVST_C_col` and `HVST_C_FLX_pft`.
- Removal loops for roots under harvest, annual death and litterfall go to `MaxNumRootLays`, one layer short of the deepest layer roots can occupy (`NK`) ([../core/grid_and_mesh.md](../core/grid_and_mesh.md) §2.5).
- Soil fire's moisture limit is inert (`VolMaxSoilMoist4Fire = 1.0`), so burn depth is set by soil organic C alone.

## Calibration parameters

None owned by these pages; see the management-field map in [disturbances.md](disturbances.md) §8.
