---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/Balances/`, the hourly conservation checks wherever they live (`f90src/ModelDiags/BalancesMod.F90`, `f90src/HydroTherm/SoilPhys/WatsubMod.F90`, `f90src/Transport/Nonsalt/`, `f90src/Plant_bgc/PlantBalMod.F90`), and the ecosystem carbon accumulators assembled in `RedistMod`
**Last verified:** 2026-10-15
---

# Mass balance, state redistribution and the column checks

`f90src/Balances/` applies the hour's fluxes to the state (`redist`), moves sediment, mixes soil at tillage and re-layers the profile. The conservation checks that can end a run are spread over five modules; this page lists all of them in the order they run within an hour, with the exact test and what happens on failure. Plant mass-balance specifics (what enters the plant budget, the root-layer range, the two fix switches) are on [../plant_bgc/roots_and_uptake.md](../plant_bgc/roots_and_uptake.md); this page summarises them.

## 1. What an abort looks like

Every check below ends the run through `endrun`, which writes `ENDRUN:` plus the message to standard output and executes a plain `stop` (`f90src/Utils/abortutils.F90:80-121`). The process therefore exits with status 0. Look for `ENDRUN:` in the log, or for the dump files the checks write first: `fort.110` (column water), `fort.111` (gas tracers), `fort.121` (transport), `fort.888` (plant C/N/P), `fort.993`-`fort.996` (WATSUB water).

## 2. Every hourly check, in execution order

| # | where it runs | routine and lines | quantity | aborts when | dump unit |
|---|---|---|---|---|---|
| 0 | `HOUR1` (`f90src/Modelforc/Hour1Mod.F90:151`) | `BegCheckBalances` (`f90src/ModelDiags/BalancesMod.F90:37-75`) | snapshot only | never | |
| 1 | inside `WATSUB`, every sub-cycle `M` | `ExitMassBalanceM` (`f90src/HydroTherm/SoilPhys/WatsubMod.F90:214-294`) | soil water + ice from `NUM` to `NL` | sub-cycle residual `abs(dwat1) > 1e-4` (`:249-252`, abort `:274`) or cumulative residual `abs(dwat) > 1e-4` (`:242-247`, abort `:276-286`) | 993, 994, 995, 996 |
| 2 | inside `PlantModel`, per column | `EnterPlantBalance` (`f90src/Plant_bgc/PlantBalMod.F90:668-711`) → `ExitPlantBalance` (`:715-735`) → `CheckPlantBalanceZ` (`:738` onward) | plant C, N, P per PFT | C: `abs(balE) > 1e-6` and (`abs(err_rel) > 1e-3`, or vegetation C below `VEGC_BAL_FLOOR_dying` when `guard_floor_dying_stand`) (`:849-852`, abort `:878`); N: `abs(balE) > 1e-6` and `abs(err_rel) > 1e-3` (`:910`); P: same test (`:919`) but not on the PFT's planting or harvest day (`:937-938`) | 888 |
| 3 | end of `TranspNoSalt` | `ExitMassCheck` (`f90src/Transport/Nonsalt/TranspNoSaltMod.F90:123-294`) | each gas in snow + litter + soil | `abs(errmass) > 1e-4` and `abs(safe_adb(errmass,delta_mass)) > 1e-3` (`:198`, abort `:286-287`) | 121 |
| 3a | transport fast sub-steps | `ExitMassCheck` (`TranspNoSaltFastMod.F90:173` onward) | | `abs(err) > 1e-4` (`:239`) | |
| 3b | transport slow sub-steps | `ExitMassCheck` (`TranspNoSaltSlowMod.F90:263` onward) | | `min(abs(err),abs(err_rel)) > 1e-5` (`:434`); `abs(err) > 1e-8` (`:460`) | |
| 4 | end of the hour | `EndCheckBalances` (`BalancesMod.F90:170-429`) | column water; gas tracers | §3 | 110, 111 |
| 4a | | | column energy | **never** (dead code, §3.3) | |

Other aborts are state sanity checks rather than balances: negative snow mass (`DealNegativeSnowMass`, `f90src/HydroTherm/SnowPhys/SnowBalanceMod.F90:329`), snow too warm (`DealHighTempSnow`, `:304`), soil temperature outside 0-1000 K (`UpdateSoilMoistTempM`, `WatsubMod.F90:1407`, `:1425`).

Not checked anywhere: total soil organic C, N, P; microbial biomass; whole-ecosystem carbon. `MicrobeModel` sums microbial biomass before and after each layer (`f90src/APIs/MicBGCAPI.F90:124-128`) into a local accumulator `tdOrGM` that is never initialised and never used, so it is not a check.

## 3. `EndCheckBalances` in detail (`BalancesMod.F90:170-429`)

It first recomputes storages with `SummarizeTracerMass` (`:196`), then per column:

### 3.1 Water

```
SoilWatErr_test = SoilWatMassBeg - SoilWatMassEnd + Qinflx2Soil - QDrain - QDischarg2WTBL
                  + TPlantRootH2OUptake + QLaterFlow2Cell                       (:204-205)
WaterErr_test   = WaterErr(beg) - WatMass(end) + PrecAtm + Irrigation + QLaterFlow2Cell
                  + RainLitr + VapXAir2GSurf + QVegET + QRunSurf - QDrain - QDischarg2WTBL
                  + TPlantRootH2OUptake - QCanopyWatLoss2Dist                    (:221-223)
```

With `fixWaterLevel` the boundary terms are dropped (`:201-202`, `:218-219`). If `abs(WaterErr_test) > err_h2o = 1e-4` (`:177`) after the first step (`etimer%get_nstep()>1`, `:230`), the budget is written to unit 110 when `iVerbLevel==1` or the soil residual also fails (`:231-271`), and the run aborts only if `abs(SoilWatErr_test) > 1e-4` (`:272-273`). A column-water miss whose soil part closes is reported but tolerated. Precipitation-partition, litter, snow and canopy residuals (`:207-216`) are computed for the dump only.

### 3.2 Gas tracers (`idg_beg..idg_NH3`)

```
tracer_mass_err = TotalMass_beg - TotalMass_end + SurfGasEmiss_all_flx + GasHydroLoss_flx
                  + solml_drib + RGasNetProd - deadroot2soil                    (:295-297)
```

NH3 adds its band pseudo-gas `idg_NH3B` (`:304-310`). A root-gas residual is computed alongside (`:301-316`). If `max(abs(tracer_mass_err), abs(tracer_rootmass_err)) > 1e-5` after the first step (`:322`), a dump goes to unit 111 when `iVerbLevel==1` or `abs(tracer_mass_err) > 0.1` (`:323-397`), and the run aborts if `abs(tracer_mass_err) > 0.1` g (`:399-400`). The comment above the block says the tracer check is "turned off momentarily" (`:287-288`); the code still aborts at 0.1. The residual is accumulated into `trcg_mass_cumerr_col` (`:318`), reset on day 1 (`f90src/Modelforc/YearMod.F90:61`).

### 3.3 Energy

`HeatErr_test` is computed (`:225-228`) but a bare `cycle` (`:407`) ends the column iteration before the energy test (`:408-425`). Energy conservation is not enforced at cb243228 (nor at `2dea74d9`).

## 4. The plant balance, summarised

`EnterPlantBalance` stores, per PFT, `TotBegVegE = Root + Shoot + SeasonalNonst + StandDead + ShootNodule + nodulE + beyondE` (`PlantBalMod.F90:684-686`), where `nodulE` and `beyondE` come from `SumRootPoolsForBalance` (`:617-665`): root nodule pools from `NU` to `LBAL` and root pools in layers `MaxNumRootLays+1..LBAL`, with `LBAL = MAX(MaxNumRootLays, MaxSoilLays4Root_pft)` (`:640`). `CheckPlantBalanceZ` forms the same total at exit (`:817-818`) and the residual

```
balE = TotEnd - TotBeg - NodulInfect - Soil2RootMycoExud + Litrfall + PlantElmDistLoss - SeedPlanted   (:820-822)
balE(C) -= GrossCO2Fix + GrossResp + beyondAR                                                         (:827)
balE(N) -= RootNutUptakeN + CanopyN2Fix + RootN2Fix + NH3Dep2Can                                     (:828)
balE(P) -= RootNutUptakeP                                                                             (:829)
```

Harvest and disturbance removals enter through `PlantElmDistLoss_pft` ([disturbances.md](disturbances.md) §2). `guard_floor_dying_stand` (default `.false.`) only relaxes the relative C test for a stand below 1 gC/m2; `conserve_root_clamp` (default `.false.`) changes what `GrowFibrous1stRootAxes` does with a negative root pool so that the C test can close. The residual is accumulated into `PlantElmBalCum_pft` (`:941-943`).

## 5. `redist`: applying the hour (`f90src/Balances/RedistMod.F90:76-156`)

Per column, in this order (`:113-149`): `AddFlux2SurfaceResidue` (`:1306`), `SinkSediments` (`f90src/Balances/ErosionBalMod.F90:28`), `ModifyExWTBLByDisturbance` (`:279`), `XGridTranspt` (`f90src/Balances/LateralTranspMod.F90:39`), `SnowMassUpdate`, `HandleSurfaceBoundary` (`:376`), `SoilErosion` (`:561`), `DiagSnowChemMass`, `LitterLayerSummary` (`:669`), `UpdateTSoilVSMProfile` (`:776`), `UpdateChemInSoilLays` (`:896`), `SnowpackLayering`, `UpdateSoilGrids` (`f90src/Balances/SoilLayerDynMod.F90:63`), `UpdateOutputVars` (`:160-274`). The boundary-solute routine `XGridBoundSolutesRunoff` is commented out (`:119`), its work now done in transport.

### 5.1 `UpdateOutputVars`: ecosystem carbon accumulators

| quantity | equation | line |
|---|---|---|
| surface gas emission | `SurfGasEmiss_all_flx_col(idg) = SurfGasEmiss_flx_col(idg) + TRootGasLossDisturb_col(idg) + trcg_air2root_flx_col(idg)` | `:172-174`, `:210-214` |
| hourly NEE | `Eco_NEE_col = Canopy_NEE_col + SurfGasEmiss_all_flx_col(idg_CO2)` | `:223` |
| hourly ecosystem respiration term | `ECO_ER_col += SurfGasEmiss_all_flx_col(idg_CO2)` | `:224` |
| NPP (within-year) | `Eco_NPP_CumYr_col = Eco_GPP_CumYr_col + Eco_AutoR_CumYr_col` | `:226` |
| NBP (within-year) | `Eco_NBP_CumYr_col += Eco_NEE_col + SurfGasEmiss_all_flx_col(CH4) + Txchem_CO2_col - HydroSufDOCFlx - HydroSufDICFlx - HydroSubsDOCFlx - HydroSubsDICFlx` | `:227-230` |
| heterotrophic respiration | `ECO_HR_CO2_col = sum(ECO_HR_CO2_vr(0:JZ))`, `ECO_HR_CH4_col = sum(ECO_HR_CH4_vr(0:JZ))`, `Eco_HR_CumYr_col += ECO_HR_CO2_col + ECO_HR_CH4_col` | `:232-234` |
| tillage | `ApplyTillageMixing(I,J,NY,NX)` | `:252` |

`SurfGasEmiss_flx_col` itself is ebullition plus surface diffusion plus wet deposition (`f90src/Transport/Nonsalt/TranspNoSaltMod.F90:164-165`, in `ExitMassCheck`). `Canopy_NEE_col` is the sum of `CO2NetFix_pft` over PFTs (`f90src/Plant_bgc/ExtractsMod.F90:407`, in `ExtractCanopyFluxes`, skipped under `ldo_sp_mode`, `:406`). A block at `:184-207` that would move gases out of layers above a raised surface sits after a `cycle` (`:190`) and never runs.

Other writers of `Eco_NBP_CumYr_col`: harvest exports (`f90src/Plant_bgc/PlantDisturbsMod.F90:630`), seed planted (`f90src/Plant_bgc/PlantPhenolMod.F90:226`), organic amendments (`f90src/Disturbances/FertilizerMod.F90:409`), soil fire and litter removal (`f90src/Disturbances/SoilDisturbMod.F90:369`, `:384`). All within-year accumulators are reset on day 1 (`YearMod.F90:53-86`).

### 5.2 History outputs built here

| tape variable | source | line |
|---|---|---|
| `CO2_SEMIS_FLX_col` (umol C m-2 s-1) | `SurfGasEmiss_all_flx_col(idg_CO2)/area * GramPerHr2umolPerSec(idg_CO2)` | `f90src/IOutils/HistData/HistUpdateColumn.F90:242` |
| `ECO_NEE_CO2_col` (umol C m-2 s-1) | `Eco_NEE_col/area * GramPerHr2umolPerSec(idg_CO2)` | `HistUpdateColumn.F90:244` |
| `ECO_RH_col` (gC m-2, within-year cumulative) | `Eco_HR_CumYr_col/area` | `HistUpdateColumn.F90:205` |
| `NBP_col` (gC m-2, within-year cumulative) | `Eco_NBP_CumYr_col/area` | `HistUpdateColumn.F90:197` |

The long name of `CO2_SEMIS_FLX_col` says "excluding wet deposition from rainfall and irrigation" (`HistRegisterColumn.F90:691-693`), but its source includes the wet-deposition term (`TranspNoSaltMod.F90:164-165`). `ECO_GPP_col` and `ECO_RA_col` are cumulative accumulators filled from the plant side (`f90src/APIs/PlantStateTransferMod.F90:58`, `f90src/APIs/PlantColumnTransferMod.F90:64`) and documented with the plant pages.

## 6. Soil relayering (`f90src/Balances/SoilLayerDynMod.F90`)

`UpdateSoilGrids` (`:63-248`) returns immediately unless `erosion_model` (`iErosionMode >= 0`, `:99`). Otherwise it flags layer-edge changes by cause (`ich_watlev=1`, `iTopLayShrink=2`, `iTopLayGrow=3`, `ich_frzthaw=4`, `ich_erosion=5`, `ich_sombgc=6`, `:48-53`), moves edges (`UpdateLayerEdges`, `:607`), and moves SOM, solutes, fertiliser, heat and water between the redefined layers (`MoveSOM` `:1456`, `MoveBandSolute` `:1714`, `MoveFertMinerals` `:1857`, `MoveHeatWat` `:2003`). It is the only code that moves `NU_col` and `NL_col` (`:206`, `:214`, `:284`, `:983`, `:1013`); `NK_col` never moves ([../core/grid_and_mesh.md](../core/grid_and_mesh.md)).

## 7. Tillage mixing (`f90src/Balances/TillageMixMod.F90`)

`ApplyTillageMixing` (`:36`) runs only when `J == INT(SolarNoonHour_col)`, `XTillCorp_col < 1` and `DepzCorp_col > 0` (`:61-62`). It caps the depth at the column thickness (`:66`), sets `iResetSoilProf_col` (`:64`), derives per-layer mixing fractions (`DeriveTillageProf`, `:597`), and mixes soil properties and pools with `Mix1D..Mix4D` (`:381-596`), keeping the fraction `XCORP0 = max(0.001, XTillCorp_col)` unmixed (`:75`). `XTillCorp_col = 1 - CORP` comes from the tillage code of the day (`f90src/Modelforc/DayMod.F90:239-248`); see [disturbances.md](disturbances.md).

## 8. Sediment sinking and lateral sums

`SinkSediments` (`f90src/Balances/ErosionBalMod.F90:28-206`) moves suspended solids and organic matter from a pond layer into the sediment at the hourly fraction `FSINK = min(1, VLS_col/DLYR)` (`:58`). `XGridTranspt` (`LateralTranspMod.F90:39`) adds the directional water, heat, solute and sediment fluxes into net cell changes; `SumSedmentTranspFlux` (`:149`) does the sediment part when erosion is on (`:160`).

## Calibration parameters

None owned here. The balance thresholds (`1e-4`, `1e-6`, `1e-3`, `0.1`) and the dying-stand floor are compile-time constants.
