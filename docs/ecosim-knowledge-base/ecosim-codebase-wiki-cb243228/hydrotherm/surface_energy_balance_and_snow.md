---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/HydroTherm/SurfPhys/`, `f90src/HydroTherm/SnowPhys/`, `f90src/HydroTherm/CanopyPhys/`, the canopy energy-water solver in `f90src/Plant_bgc/UptakesMod.F90`, ground radiation and roughness in `f90src/Plant_bgc/SurfaceRadiationMod.F90`, ET bookkeeping in `f90src/Balances/RedistMod.F90` and `f90src/Plant_bgc/ExtractsMod.F90`
**Last verified:** 2026-10-15
---

# Surface energy balance, evapotranspiration and snow

This page traces the evapotranspiration output `ECO_ET_col` to every equation that produces it, then documents each surface process in turn. See [index.md](index.md) for the hourly call order and [subsurface_water_and_heat.md](subsurface_water_and_heat.md) for the soil column. Sign convention throughout: a vapour flux "Air2X" is positive into the surface (condensation) and negative for evaporation.

## 1. ECO_ET_col: producing equation and decomposition

### 1.1 The output and its accumulator

```
ECO_ET_col [mm]   = m2mm * QEvap_CumYr_col / AREA                      HistUpdateColumn.F90:213 (update_hist_columns)
QEvap_CumYr_col  -= WO,   WO = VapXAir2GSurf_col + QVegET_col          RedistMod.F90:408-410 (HandleSurfaceBoundary)
EvapoTransp_col   = -WO                                                RedistMod.F90:411
QEvap_CumYr_col   = 0  on day I = 1                                    YearMod.F90:53, :68 (SetAnnualAccumlators)
```

`ECO_ET_col` is registered as "cumulative total evapotranspiration" with avgflag `I` (`f90src/IOutils/HistData/HistRegisterColumn.F90:560-561`): each history record is the running year-to-date total at that instant, not a rate. A daily or hourly ET comparison needs differences of successive records, and the series restarts at zero on day 1 of each year. Both terms of `WO` are hourly sums zeroed in `SetHourlyDiagnostics` (`f90src/Modelforc/Hour1Mod.F90:800`, `:810`).

### 1.2 The two terms

```
VapXAir2GSurf_col = sum over M=1..NPH of [ VapXAir2TopLay + VapXAir2Sno_col ]    SurfPhysMod.F90:1096 (AccumWaterVaporHeatFluxesM)
                  + sum over M of VapXAir2LitR                                   SurfPhysMod.F90:1596 (SumAftEnergyBalanceM)
QVegET_col        = sum over active PFTs of [ Transpiration_pft + VapXAir2Canopy_pft ]   ExtractsMod.F90:398 (ExtractCanopyFluxes)
VapXAir2Canopy_pft = VapXAir2CanopyLiq_pft + SnoSub2AirCanopy_pft               UptakesMod.F90:886 (CanopyEnergyH2OIter_func)
```

So `ECO_ET_col` decomposes into five fluxes, each documented below:

| Component | Variable | Produced at | Output field |
|---|---|---|---|
| Canopy transpiration | `Transpiration_pft` | `UptakesMod.F90:899` (§3) | `QVegTransp_pft`, `QTransp_col`, `STOM_RSC_H2O_pft` |
| Interception evaporation, canopy dew | `VapXAir2CanopyLiq_pft` | `UptakesMod.F90:858`, `:876` (§3) | `QVegEvap_col` (= `VapXAir2Canopy_col`, liquid + snow) |
| Canopy snow sublimation | `SnoSub2AirCanopy_pft` | `UptakesMod.F90:882` (§3) | inside `QVegEvap_col` |
| Bare-soil evaporation, condensation | `VapXAir2TopLay` | `SurfPhysMod.F90:587` (§7) | `EVAPGrnd_col` (= `VapXAir2GSurf_col`) |
| Litter evaporation | `EvapAtm2LitR2` summed into `VapXAir2LitR` | `SurfLitterPhysMod.F90:370`, `:446` (§8) | inside `EVAPGrnd_col` |
| Snow evaporation and sublimation | `EVAPW2 + EvapSublimation2` into `VapXAir2Sno_col` | `SnowPhysMod.F90:847-851`, `:886` (§9) | inside `EVAPGrnd_col` |

History mapping (`HistUpdateColumn.F90`, `update_hist_columns`; `HistUpdatePlant.F90`, `update_hist_plants`): `EVAPGrnd_col = VapXAir2GSurf_col*m2mm/AREA` (`HistUpdateColumn.F90:271`); `QVegEvap_col` from `VapXAir2Canopy_col` (`:273`); `QVegET_col` from `QVegET_col` (`:274`); `QVegTransp_pft` from `Transpiration_pft` and `QTransp_col` its sum (`HistUpdatePlant.F90:179-180`); `tTRANSPN_pft = -ETCanopy_CumYr_pft*m2mm/AREA`, a year-to-date canopy ET (`:95`; accumulator at `ExtractsMod.F90:394`). Latent heat: `ECO_LE_col = Eco_Heat_Latent_col`, the sum of `CanopyEvapTransLHeat_pft` over PFTs (`ExtractsMod.F90:391`) plus the ground `HeatEvapAir2Surf_col` (`RedistMod.F90:217`, `UpdateOutputVars`); `SOIL_LE_col = HeatEvapAir2Surf_col` (`HistUpdateColumn.F90:234`); `CAN_LE_pft = CanopyEvapTransLHeat_pft` (`HistUpdatePlant.F90:149`).

### 1.3 What drives which term

- The canopy terms exchange with the **reference-height** air: `EX = CdVapCanopyAir*(VPA - VPLeaf)` with `VPA = VPA_col` (`UptakesMod.F90:857`; `f90src/APIs/PlantAPI4Uptake.F90:84`).
- The ground, litter and snow terms exchange with **canopy air** `VPQ_col`, which is the forcing vapour minus last hour's total latent flux times resistance (`SurfPhysMod.F90:275`, `SetCanopyProperty`; stores accumulated at `UptakesMod.F90:220` and `RedistMod.F90:221`). A dense, transpiring canopy therefore humidifies the air the ground sees one hour later.
- `PlantModel` runs after `watsub` in the same hour (`drivers/ecosim/EcoSIMAPI.F90:56`, `:73`), and root uptake is withdrawn from the soil one hour after it is booked as transpiration (see [index.md](index.md#where-hydrotherm-runs-in-the-hour)).

## 2. Canopy interception of rain and snow

`CanopyInterceptPrecip` (`f90src/HydroTherm/CanopyPhys/CanopyHydroMod.F90:25-102`) runs once per hour from `hour1` (`Hour1Mod.F90:238`). For each PFT with leaf+stalk area `LeafStalkAreaAct_pft > 0` (`:56`):

```
CanopyWatHeldCap  = FoliarWatRetcap(IGTYP class) * LeafStalkAreaAct_pft          :57
CanopySnowHeldCap = FoliarSnowRetcap(ISNTYP class) * LeafStalkAreaAct_pft        :58
rain2canopy = PrecRainAndIrrig_col * FracPARads2Canopy_pft                        :61
snow2canopy = SnoFalPrec_col * FracPARads2Canopy_pft                             :60
RainIntcptByCanopy_pft = max(0, min(rain2canopy, CanopyWatHeldCap - WatHeldOnCanopy_pft))   :63
SnowIntcptByCanopy_pft = max(0, min(snow2canopy, CanopySnowHeldCap - SnowOnCanopy_pft))     :62
SnowWindUnload = WindSpeedAtm_col * SnowOnCanopy_pft / 1.56E5                    :69
SnowTempUnload = SnowOnCanopy_pft * max(0, TKCanopy_pft - 270) / (1.87E5*3600)   :71
```

Retention constants (`:19-21`): `FoliarWatRetcap(0:3) = 5.0E-4, 2.5E-4, 2.5E-4, 2.5E-4` m per unit leaf+stalk area, indexed by `iPlantRootProfile_pft`, which is read from the plant-file flag IGTYP (0 shallow, 1 intermediate, 2 deep; `f90src/IOutils/PlantInfoMod.F90:1724`, `ReadPlantTraitTable`), so index 3 is unreachable; `FoliarSnowRetcap(0:4) = 1.0E-4, 2.0E-4, 3.0E-4, 2.0E-3, 7.0E-3` and `BulkFactor4Snow(0:4)` indexed by `iPlantSnowIntercepType_pft`, read from ISNTYP (0 bryophyte, 1 grass, 2 shrub, 3 deciduous tree, 4 conifer; `PlantInfoMod.F90:1745`, copied per PFT at `:741`, `SetPlantTraits`). `fSnowCanopy_pft = min(1, ((SnowOnCanopy+SnowIntcpt)/CanopySnowHeldCap)**0.15)` (`:79`) is the snow-covered canopy fraction (output `fSnowCanopy_pft`).

Throughfall is `RainPrecThrufall_col = PrecRainAndIrrig_col - RainIntceptByCanopy_col` and `SnowPrecThrufall_col = SnoFalPrec_col - SnowIntceptByCanopy_col + CanopySnowUnload_col` (`:90-91`), with the unloaded snow carrying the canopy temperature into `TKSnowThrufall_col` (`:92-96`). `PartitionPrecip` then splits throughfall among snow, litter, soil micropores and macropores by the cover fractions (`SurfPhysMod.F90:1403-1414`) and uses `TKSnowThrufall_col` for the snowfall heat (`:1407`). The code comment at `CanopyHydroMod.F90:48` ("No snofall intercepation is considered") is stale.

Canopy water is not drained: held water leaves only by evaporation, and the stores are updated after the energy balance, `WatHeldOnCanopy_pft += RainIntcptByCanopy_pft + VapXAir2CanopyLiq_pft` and `SnowOnCanopy_pft += SnowIntcptByCanopy_pft + SnoSub2AirCanopy_pft` (`UptakesMod.F90:1524-1525`, `UpdatePlantWaterVars`).

## 3. Canopy transpiration, interception evaporation and dew

`RootUptakes` (`Plant_bgc/UptakesMod.F90:51-240`) treats each active PFT. A PFT is hydraulically active only after emergence, with leaf+stalk area and PAR, a primary root below the seeding depth and positive canopy C (`:165-169`); otherwise `HandleBareSoil` sets transpiration, canopy evaporation and dew to zero (`:1406-1414`). The canopy footprint is `FracGridPFTCovered = LeafStalkAreaAct_pft/LeafStalkAreaAll_col * min(1, 0.5*CanopyLeafArea_col/AREA)` (`:185`).

Inside `CanopyEnergyH2OIter_func` (`:654-1157`), each iteration (up to `MaxIterNum = 200`, `UptakePars.F90:41`):

```
RadNet2Canopy_pft = RadSWCanopyAbsorption_pft + LWRad2Canopy - 2*FTHRM*TKC^4          :810-812
RawCanopy2Atm_pft = max(MinRawCanopy2Atm_pft, 0.9*RA1, min(1.1*RA1, RawIsoTCanopy2Atm_pft/(1-10*RI)))   :822
CdVapCanopyAir    = FracGridPFTCovered*AREA / RawCanopy2Atm_pft                         :787, :824
CanPStomaResistH2O_pft = CalcStomataResist4H2O(NZ)                                       :837
VPLeaf = vapsat(TKC) * exp(18*max(PSICanopy_pft,-5000)/(RGASC*TKC))                     :854
EX     = CdVapCanopyAir * (VPA - VPLeaf)                                                :857
VapXAir2Canopy_pft = EX * Rb/(Rb + ResistLeafSurf)                                      :858
```

with `Rb = RawCanopy2Atm_pft`, `MinRawCanopy2Atm_pft = 0.00139` h/m and `ResistLeafSurf = 0.0139` h/m, the surface resistance of wet leaves (`f90src/Plant_bgc/UptakePars.F90:45`, `:47`). Then three branches:

- **Dew** (`EX > 0`, `:862-867`): the whole condensation goes to the canopy surface (`QdewCanopy_pft`, `VapXAir2CanopyLiq_pft`), `EX` is set to 0, so there is no transpiration that iteration.
- **Evaporation of held water and snow** (`EX <= 0` and the canopy held water or snow at the start of the hour, `:871-887`): liquid evaporation `VapXAir2CanopyLiq_pft = max(VapXAir2Canopy_pft, -WatHeldOnCanopy_pft)` (`:876`), then sublimation of the remainder `SnoSub2AirCanopy_pft = max(rest, -SnowOnCanopy_pft)` (`:882`), and the transpiration demand is reduced by what was evaporated (`EX = EX - VapXAir2Canopy_pft`, `:887`). Water intercepted in the current hour is added to the store only afterwards (`:1524`), so it cannot evaporate in the hour it falls unless the canopy was already wet.
- **Dry canopy** (`:888-893`): canopy evaporation is zero and `EX` is the full demand.

```
Transpiration_pft        = EX * Rb/(Rb + CanPStomaResistH2O_pft)                                 :899
CanopyEvapTransLHeat_pft = (Transpiration_pft + VapXAir2CanopyLiq_pft)*EvapLHTC + SnoSub2AirCanopy_pft*SublmHTC   :900
```

`EvapLHTC = 2465` kJ/kg and `SublmHTC = LtHeatIceMelt + EvapLHTC` (`f90src/Utils/EcoSimConst.F90:29-30`). The canopy temperature is solved from the balance of net radiation, latent heat, the enthalpy of evaporated or condensed water, precipitation heat and root-water heat (`:908`, `:919-924`) and kept within 5 K of air (`:927`).

**Where stomatal resistance enters.** `CalcStomataResist4H2O` (`f90src/Plant_bgc/PlantMathFuncMod.F90:555-572`) returns `Rs = Rmin + (Rcut - Rmin)*exp(-PSICanopyTurg_pft/RCS_pft)` (`:569-570`). `Rcut = H2OCuticleResist_pft = RSMX/3600` (`f90src/Ecosim_mods/StartqMod.F90:176`, `InitShootGrowth`; `f90src/Plant_bgc/InitPlantMod.F90:189`); `Rmin = CanopyMinStomaResistH2O_pft` comes from the photosynthesis-limited CO2 resistance, bounded by `Rcut` (`f90src/Plant_bgc/StomatesMod.F90:1065`, `PhotoActivePFT`), and equals `Rcut` at night (`:275`, `StomatalDynamics`). Turgor is `PSICanopyTurg_pft = max(0, PSICanopy - PSIOsmo)` with `PSIOsmo = FDMP*(OSMO/FDMP0 - RGASC*T*CCPOLT/OSWT)` (`PlantMathFuncMod.F90:69-72`, `update_osmo_turg_pressure`, called at `UptakesMod.F90:832`). `StomatalDynamics` is re-called when the water iteration converges (`:1074`, `:1126`). The photosynthesis side of `Rmin` belongs to the plant photosynthesis page.

**Supply side.** Each iteration checks transpiration against root uptake and canopy water storage and moves `PSICanopy_pft` until they agree (`:962-1137`); root uptake per layer is `(PSILC - PSIsoil)/SoilRootResist4H2O_pvr` limited by available water and air space (`:985-993`). The hydraulic resistances and the uptake are documented in [../plant_bgc/roots_and_uptake.md](../plant_bgc/roots_and_uptake.md#8-root-water-uptake-and-its-link-to-et). If the iteration fails with `DIFF > 0.5`, `HandlingDivergence` zeroes the PFT's transpiration and canopy evaporation for that hour (`UptakesMod.F90:603-613`).

The canopy outputs `STOM_RSC_H2O_pft = CanPStomaResistH2O_pft*3600` and `BLYR_RSC_H2O_pft = RawCanopy2Atm_pft*3600` [s/m] are written at `HistUpdatePlant.F90:176-177`.

## 4. Surface staging and cover fractions

`StageSurfacePhysModel` (`SurfPhysMod.F90:114-173`) runs once per hour before the `watsub` loop (`WatsubMod.F90:130`): `StageSnowModel` (`:156`), `CopySurfaceVars` (`:158`, litter heat capacity `cpo*m3OM + cpw*water + cpi*ice` at `:198`), `PartionSurfaceFraction` (`:160`), `PartitionPrecip` (`:162`), `SurfaceResistances` (`:164`), `Radiation2Surface` (`:166`), `SetCanopyProperty` (`:168`).

```
FracSurfAsSnow_col  = min(1, sqrt(SnowDepth_col/MinSnowDepth)),  MinSnowDepth = 0.075 m     SurfPhysMod.F90:252; PhysPars.F90:31
FracSurfSnoFree_col = 1 - FracSurfAsSnow_col                                               :253
FracSurfBareSoil_col = min(1, max(exp(-0.8E-2*SoilOrgM_litter_C/AREA), XVLMobileWaterLitR/VLWatHeldCapSurf))   SurfLitterPhysMod.F90:54-55
FracSurfByLitR_col  = 1 - FracSurfBareSoil_col                                             SurfLitterPhysMod.F90:64
```

The litter fraction is recomputed at the start of each iteration (`InitSurfModelM`, `SurfPhysMod.F90:1140`); free water ponded above the litter's holding capacity raises the bare fraction.

## 5. Aerodynamic resistances and ground roughness

**Canopy roughness and the above-canopy resistance** are computed in the canopy radiation model each hour (`f90src/Plant_bgc/SurfaceRadiationMod.F90:82-183`, `CalcBoundaryLayerProperties`):

```
ZE = CanopyHeight * max(0.05, ZX*ZY),  ZX = exp(-0.5*ARLSG), ZY = 1-ZX              :128-130
ZeroPlaneDisplacem_col = CanopyHeight * max(0, 1 - 2/ARLSG*ZY)                      :132
RoughnessLength = max(0.001, ZE, ZW)                    snow-covered                :147
RoughnessLength = max(0.001, ZE, SoilSurfRoughness_col) snow-free                   :149
RawIsoTAtm2CanopySinkZ_col = max(RAM, ln((ZWind-d)/z0)^2 / (0.168*WindSpeedAtm))   :159
RIB = 1.27E8*(ZWind - z0)/(WindSpeedAtm^2 * TairK)                                 :175
```

`ARLSG` is leaf + stem + standing-dead area per ground area (`:123`, `:127`); the canopy only counts while it is taller than the snow (`:125`).

**Ground roughness is hard-coded.** `SoilSurfRoughness_col = 0.020 m` when the surface layer has bulk density, otherwise `ZW` (`f90src/Modelforc/Hour1Mod.F90:614-619`, `ResetSurfResidualProperty`), with `ZW = 0.01 m` (`EcoSimConst.F90:47`, "snowpack surface roughness"). No plant, microbial or grid file parameter reaches it. Besides the two uses above it sets the surface water-holding capacity `VLWatHeldCapSurf_col = max(0.001, 0.112*z0 + 3.10*z0^2 - 0.012*z0*slope)*AREA` (`Hour1Mod.F90:621-623`) and is the base of the overland-flow roughness `SoiSurfRoughness`, which adds a texture term and the litter depth (section 10.1).

**Below-canopy resistance** (`SurfPhysMod.F90:355-443`, `SurfaceResistances`), Choudhury and Monteith (1988) with `ALFZ = 2*(1 - FracSWRad2Grnd_col)` (`:379`):

```
RawIsoTSurf2SinkZ_col = min(RACX, max(0, h*exp(ALFZ)/(ALFZ/RawIsoTSurf2CanopyHScal) *
                        max(0, exp(-ALFZ*SoilSurfRoughness/h) - exp(-ALFZ*(d+z0)/h))))     :385-387
RawIsoTSoil2ATM_col      = RawIsoTSurf2SinkZ_col + RawIsoTAtm2CanopySinkZ_col            :420
ResistAreodynOverSnow_col = RawIsoTSoil2ATM_col                                          :421
ResistAreodynOverLitr_col = RawIsoTSoil2ATM_col + ResistanceLitrSurf (0.0139 h/m)         :422; :62
```

`RACX = 0.0139` h/m here is an upper cap (`SurfPhysMod.F90:66`); a different constant with the same name, `RACX = 0.0278` h/m, caps the canopy-to-sink resistance of shorter PFTs (`UptakePars.F90:46`; used at `UptakesMod.F90:396-398`, `UpdateCanopyProperty`). The canopy-air resistance gets the Richardson correction `RawTAtm2CanopySinkZ_col = max(RAM, 0.8*R, min(1.2*R, R/(1-10*RI)))` (`SurfPhysMod.F90:281`).

Conductance prefactors (`:427-436`): `PAREX = AREA*dts_HeatWatTP` [m2 h] and `PARSX = 1.25E-3*AREA*dts_HeatWatTP` (air heat capacity 1.25E-3 MJ m-3 K-1). Snow latent/sensible: `PAREX*FracSurfAsSnow*XNPS`; **bare soil: `PAREX*FracSurfSnoFree` (the whole snow-free area, not the bare-soil fraction)**; litter: `PAREX*FracSurfSnoFree*FracSurfByLitR*XNPR`.

## 6. The litter vapour-resistance chain

The litter layer adds a diffusive resistance in series, and the bare-soil evaporation conductance is built from it:

```
VaporDiffusivityLitR_col = TEFGASDIF(TKS_litter) * 7.70E-2   [m2/h]           SurfPhysMod.F90:416-417 (SurfaceResistances)
   TEFGASDIF(T) = (T/298.15)**1.75                                             f90src/Minimath/MiniFuncMod.F90:74
VapDiffusResistanceLitR  = DLYRR_COL / VaporDiffusivityLitR_col                :418
   DLYRR_COL = max(2.5E-3, litter thickness)                                   :1385 (PartitionPrecip)
VaporTortuosityLitr = thetaA_litter * POROQ * thetaA_litter / POROS_litter      :425, :555;  POROQ = 0.66 (EcoSimConst.F90:38)
ResistanceLitRLay   = RawIsoTSoil2ATM_col + VapDiffusResistanceLitR/VaporTortuosityLitr    :426, :556
ResistBndlSurf0     = 1 / ((1-fLit)/ResistAreodynOverLitr_col + fLit/ResistanceLitRLay)    :559 (SoilSRFEnerbyBalanceM)
ResistBndlSurf_col  = max(RAM, 0.8*R0, min(1.2*R0, ResistanceLitRLay/(1-10*RI)))           :564
RAa                 = ResistAreodynOverLitr_col + ResistBndlSurf_col                       :565
CdSoiEvap           = AScaledCdWOverSoil_col / (RAa + RZ),   RZ = 0.0139 h/m                :580; PhysPars.F90:33
```

`fLit = FracSurfByLitR_col`; `thetaA_litter` is the litter air-filled porosity, reduced by mobile water above the holding capacity (`SurfPhysMod.F90:224-225`). Thick, wet litter therefore suppresses bare-soil evaporation; with no litter `ResistBndlSurf0 = ResistAreodynOverLitr_col` and the chain reduces to two aerodynamic resistances plus `RZ`. The litter thickness in `DLYRR_COL` is `DLYR_3D(3,0) = VLSoilPoreMicP_vr(0)/AREA` with `VLSoilPoreMicP_vr(0) = VGeomLayer_vr(0) = VxcessWatLitR + VLitR_col` (`f90src/Modelforc/Hour1Mod.F90:1428-1431`, `:1457`, `GetSurfResidualProperties`), so the dry litter volume `VLitR_col` of section 10.1 sets the vapour diffusion path as well as the runoff roughness.

A second combination of the same resistances, weighted by the exposed-soil fraction `FracAsExposedSoil_col` instead (`SurfPhysMod.F90:1144-1152`, `InitSurfModelM`), sets the soil-air gas conductance used by transport: `CondGasXSnowM_col = AREA*dts_HeatWatTP/(ResistBndlSurf_col + RAS)` and `CondGasXSurf_col = 1/(ResistBndlSurf_col + RAS)` (output `GasXSurfConduct_col`), where `RAS` is the snowpack diffusion resistance (`:1154-1156`). The litter chain therefore also throttles CO2, CH4 and O2 exchange (see [../transport/gas_transport.md](../transport/gas_transport.md#3-atmospheric-boundary)).

## 7. Ground radiation and the bare-soil energy balance

### 7.1 Radiation onto the ground

The canopy model delivers the shortwave reaching the ground, `RadSWGrnd_col = RadSW2Ground*AREA` (`SurfaceRadiationMod.F90:567`, `SurfaceRadiation`). HydroTherm splits it by cover (`SurfPhysMod.F90:314-326`, `Radiation2Surface`; `:339-349`, `LiterSoilRadiationM`):

```
RadSW2Soil_col = RadSWGrnd_col*dts_HeatWatTP*FracSurfSnoFree*FracSurfBareSoil       :340
LWRad2Soil_col = (LWRadSky_col*FracSWRad2Grnd_col + LWRadCanGPrev_col)*dts_HeatWatTP*FracSurfSnoFree*FracSurfBareSoil   :343-344
LWEmscefSoil_col = 0.97*stefboltz_const*AREA*FracSurfSnoFree*FracSurfBareSoil*dts_HeatWatTP   :348; emissivities :63-65
```

### 7.2 Ground albedo: grid ALBS to net radiation

ALBS is read from the grid file into `SoilAlbedo_col` (`f90src/IOutils/readimod.F90:440`, `readTopoNC`; copied to all columns at `:553`). Its declaration comment says "snowpack albedo" (`f90src/Ecosim_datatype/SnowDataType.F90:15`), but it is the soil-surface albedo; the reader's own comment calls it "wet soil albedo" (`readimod.F90:543`). In the bare-soil energy balance (`SurfPhysMod.F90:518-538`, `SoilSRFEnerbyBalanceM`):

```
AlbedoGrnd = (ALBS*VLSoilMicPMass + 0.06*VLWatGrnd + 0.30*VLIceGrnd) / (VLSoilMicPMass + VLWatGrnd + VLIceGrnd)   :525-526
AlbedoGrnd = ALBS                       if the top layer has no water or ice                                      :529
RadSWbySoil  = (1 - AlbedoGrnd)*RadSW2Soil_col                                                                    :534
Radnet2Grnd  = RadSWbySoil + LWRad2Soil_col - LWEmscefSoil_col*TKSoil1^4                                          :535-537
```

`VLWatGrnd`, `VLIceGrnd` sum micropore and macropore water and ice of the top layer (`:518-519`). `Radnet2Grnd` is accumulated into `HeatByRad2Surf_col` (`:1083`), which is `SOIL_RN_col` (`HistUpdateColumn.F90:232`) and is added to the canopy net radiation in `Eco_NetRad_col` (`RedistMod.F90:216`), i.e. `ECO_Radnet_col` (`HistUpdateColumn.F90:237`); the absorbed shortwave goes to `Eco_RadSW_col` (`SurfPhysMod.F90:538`), i.e. `ECO_RADSW_col`.

**The canopy radiation model uses a different ground albedo.** For radiation reflected back into the canopy, `RadiationAtGround` uses `GrndAlbedo = FracGrndBySnow*SnowpackAlbedo + (1-FracGrndBySnow)*SoilAlbedo` with `FracGrndBySnow = min(1, (SnowDepth/0.07)**2)` under snow, and `GrndAlbedo = min(SurfAlbedo_col, SoilAlbedo + max(0, SurfAlbedo_col - THETW1))` without (`SurfaceRadiationMod.F90:1350-1363`). `SurfAlbedo_col` is set once to `SoilAlbedo_col` (`f90src/Ecosim_mods/StartsMod.F90:833`, `InitAccumulators`) and never updated, so the snow-free `GrndAlbedo` equals ALBS whatever the soil moisture. The two albedos agree only for a dry surface.

Litter albedo is fixed by composition, `0.20` dry litter, `0.06` water, `0.30` ice (`SurfLitterPhysMod.F90:138-139`); snow albedo is `(0.85*dry + 0.30*ice + 0.06*water)/total` unless `mod_snow_albedo` (`SnowPhysMod.F90:800-805`).

### 7.3 Bare-soil evaporation and condensation

```
PSISV1    = PSISM1(top) + PSISoilOsmotic(top)                                 SurfPhysMod.F90:503-505
VaporSoi1 = vapsat(TKSoil1) * exp(18*PSISV1/(RGASC*TKSoil1))                  :583
VapXAir2TopLay = max(CdSoiEvap*(VPQ_col - VaporSoi1), -TopLayWatVol*dts_wat)  :587
LatentHeatEvapAir2Grnd = VapXAir2TopLay*EvapLHTC                              :591
HeatSensVapAir2Grnd = VapXAir2TopLay*cpw*T*HeatAdv_scal, T = TKSoil1 (evap) or TKQ_col (condensation)   :592-598
HeatSensAir2Grnd = CdSoiHSens_col*(TKQ_col - TKSoil1),  CdSoiHSens_col = AScaledCdHOverSoil_col/RAa     :581, :610
HeatFluxAir2Soi  = Radnet2Grnd + LatentHeatEvapAir2Grnd + HeatSensAir2Grnd + HeatSensVapAir2Grnd        :611-612
```

The soil surface vapour pressure follows the Kelvin relation on matric plus osmotic potential, so a drying surface self-limits evaporation; the cap `-TopLayWatVol*dts_wat` stops it emptying the layer. `HeatFluxAir2Soi` is the top-layer boundary heat flux; the soil temperature update treats long-wave emission and sensible heat semi-implicitly through `dHGrnddTKsoi1 = -4*LWEmscefSoil*TKSoil1^3 - CdSoiHSens_col` (`:1653`, `RunSurfacePhysModelM`; used at `WatsubMod.F90:1376-1378`). These fluxes are computed only when part of the ground is snow-free and the top layer is soil or has heat capacity (`SurfPhysMod.F90:731-738`, `AtmLandSurfExchangeM`); under full snow cover they are zero (`ZeroFlxOverSnowCoveredSoilM`, `:767-788`).

## 8. Litter energy balance and evaporation

`SurfLitREnergyBalanceM` (`SurfLitterPhysMod.F90:69-183`) runs when `FracSurfByLitR_col > ZEROL` (`:135`). It forms the litter-soil vapour conductance `CdVaporLit2Soil` from the litter and soil air-filled tortuosities (`:146-155`), the litter-soil thermal conductance from `CalcLitRThermConductivity` (`:186-215`) and `CalcSoilThermConductivity` (`:159-163`), and calls `SurfLitterIterationM` (`:219-491`), which sub-steps `NPR` times with `dt_litrHeat = dts_HeatWatTP/NPR` (`:291`):

```
ResistAreodynOverLitr_col = max(RAM, 0.8*RAGX, min(1.2*RAGX, RawIsoTLitr2ATM_col/(1-10*RI)))   :316
CdLitREvap  = AScaledCdWOverLitr_col/(ResistAreodynOverLitr_col + RZ)                           :317
CdLitRHSens = AScaledCdHOverLitr_col/ResistAreodynOverLitr_col                                  :318
VapLitR = vapsat(TKR1)*exp(18*PSISM1_litter/(RGASC*TKR1))                                       :358
EvapAtm2LitR2 = max(-VWatLitr2*dts_wat, CdLitREvap*(VPQ_col - VapLitR))                         :370
FLVC = CdVaporLit2Soil*(VapLitR - VaporSoi1)*AREA*FracSurfSnoFree*FracSurfByLitR*dt_litrHeat   :392
HeatSensAir2LitR2 = CdLitRHSens*(TKQ_col - TKR1)                                                :439
```

The litter matric potential uses the same piecewise log-log curve as soil, with the litter's FC/WP (`:341-356`). `EvapAtm2LitR2` sums into `VapXAir2LitR` (`:446`), which goes into ET; the litter-soil vapour flux `EvapLitR2Soi2` (`:399-411`) is internal and does not. Litter and top-soil temperatures are updated semi-implicitly in long-wave emission and sensible heat (`:484-485`); the hourly litter temperature after runoff is solved the same way, with a re-linearised derivative when the change exceeds 10 K (`SurfLitterPhysMod.F90:620-630`, `UpdateLitRBe4RunoffM`).

## 9. Snowpack

**Layers.** Up to `JS = 5` layers with reference cumulative depths 0.05, 0.15, 0.30, 0.60, 1.00 m (`SnowPhysMod.F90:66`, `InitSnowLayers`); new-snow density 0.10 Mg m-3 (`:89`); minimum heat capacity `VLHeatCapSnowMin_col = VLHeatCapSnoMin*AREA` gates all snow fluxes (`:147`).

**Snow-atmosphere exchange** (`SnowAtmosExchangeMM`, `:765-909`), called `NPS` times per iteration from `SolveSnowpackM` (`:548`, `:554`):

```
RadSWbySnow = (1 - SnowAlbedo)*RadSW2Sno_col                                     :807
RAa = max(RAM, 0.8*R, min(1.2*R, RawIsoTSoil2ATM_col/(1-10*RI)))                  :824-827
CdSnoEvap = AScaledCdWOverSnow_col/(RAa + RZ)                                     :841
MaxVapXAir2Sno = CdSnoEvap*(VPQ_col - vapsat(TKSnow1(1)))                         :843-844
EVAPW2 = max(MaxVapXAir2Sno, -VLWatSnow0M(1)*dts_sno)            liquid first     :847
EvapSublimation2 = max(min(0, MaxVapXAir2Sno - EVAPW2), -VLDrySnoWE0M(1)*dts_sno) then dry snow   :849-851
LatentHeatAir2Sno2 = EVAPW2*EvapLHTC + EvapSublimation2*SublmHTC                  :852
VapXAir2Sno_col += EvapSublimation2 + EVAPW2                                      :886
```

The snow surface is assumed saturated (no Kelvin term, `:843`). Condensation and deposition are not split: when `MaxVapXAir2Sno > 0` the whole gain goes to `EVAPW2` (`:847`, `:849`). `VapXAir2Sno_col` is reset each iteration (`InitSnowAccumsM`, `:200`, called from `SurfPhysMod.F90:1265`).

**Snowpack resistance** for gas and vapour, `RAS = sum over layers of (thickness/H2OVapDifsc)/max(ZERO, air fraction)**2` (`CalcSnowBNDResistance`, `SnowPhysMod.F90:1369-1403`).

**Layer solver and freeze-thaw.** `SolveSnowpackM` (`:482-763`) uses `dt_snoHeat = dts_HeatWatTP*XNPS` (`:541`); per layer (`D9860`, `:573`) the latent-heat-limited phase change is `TFLX1 = VLHeatCapSnowMX*(TFice - TKApp)/2.7185*dts_wat` (`:652`), bounded by the ice available to melt (`:663`) or the water available to freeze (`:670`); masses are floored at `tinyw0 = 1E-16` (`:711-713`), and a temperature jump above 20 K or below 200 K aborts with "crazy snow temperature" (`:731-740`). Hourly closure and re-layering are `SnowMassUpdate` and `SnowpackLayering` (`SnowBalanceMod.F90:57`, `:549`), called from `redist` (`RedistMod.F90:127`, `:145`).

**Snow-litter and snow-soil exchange.** When litter covers the ground the bottom snow layer exchanges vapour and heat with litter, and litter with soil (`SnowSurLitterExch`, `SnowPhysMod.F90:1720-1815`, inner loop `D4000` over `NPR` at `:1468`); otherwise with the top soil directly (`SnowTopSoilExch`, `:1819-1927`). These fluxes are internal and do not enter ET.

## 10. Infiltration, runoff and surface energy outputs

`InfilSRFRoffPartitionM` (`SurfPhysMod.F90:938-1042`) handles litter freeze-thaw, with the Clausius-Clapeyron freezing point and denominator `(1 + (TFREEZ-TFICE)*6.2913E-3)*(1 - 0.10*PSISM1)` (`:984-985`), and splits surface water into infiltration and runoff. `GaucklerManningVelocity` returns `HydraulicRadius**0.67*sqrt(slope)` with no roughness coefficient of its own (`:1700-1714`), and its caller divides the result by the surface roughness `SoiSurfRoughness`, which plays the part of Manning's n (`:1031`; section 10.1). Rainfall kinetic energy reduces the top-layer Ksat through `RainEkReducedKsat = exp(-2E-3*(silt+clay)*EnergyImpact4Erosion)` (`:1260-1261`, `InitSurfModelM`).

### 10.1 Surface litter volume, surface roughness and overland flow

The chain from surface litter C to runoff velocity at cb243228:

```
SurfLitterC_col(K) = litter-layer (L=0) C of complex K: solid OM + microbial residue + live heterotrophs
                     + DOM (micro- and macropore) + sorbed OM + acetate                   MicrobialDiagMod.F90:412-437 (sumSurfOMCK)
                     summed at the end of each hour                                       RedistMod.F90:686 (LitterLayerSummary, from redist :137)
VLitR_col          = AZMAX1(ppmc * sum_K SurfLitterC_col(K)/BulkDensLitR(K))             Hour1Mod.F90:1675-1682 (UpdateLiterPropertz, from hour1 :142)
  BulkDensLitR     = (0.0333, 0.0167, 0.0167) Mg m-3 for woody, fine, manure             StartsMod.F90:744 (InitControlParms)
  ppmc             = 1.0E-06 (g to Mg, so the volume is in m3)                           f90src/Utils/EcoSimConst.F90:55
D50                = 1.0*CCLAY + 10*CSILT + 100*CSAND + 100*CORGM   (surface layer NU)    Hour1Mod.F90:920-921 (SetSurfaceProp4SedErosion, from hour1 :154)
ZD50               = 0.041*(ppmc*D50)**0.167                                              :922
SoiSurfRoughness   = SoilSurfRoughness_col + ZD50 + 1.0*VLitR_col/AREA_3D(3,0)           :923
CrossSectVelocity  = GaucklerManningVelocity(HydraulicRadius, SLOPE)/SoiSurfRoughness    SurfPhysMod.F90:1031 (InfilSRFRoffPartitionM)
  only when XVLMobileWaterLitR > VWatStoreCapSurf; HydraulicRadius = (excess water depth)/2.828   :1027-1030
Q                  = CrossSectVelocity*WatExcessDetph*AREA*secsphour*dts_HeatWatTP       :1032
RunoffVelocityM_col = CrossSectVelocity                                                   :1034
SurfRunoffPotentM_col = AMIN1(Q, VWatExcess*dts_wat, VLWatMicP1X*dts_wat)*XVLMobileWatMicP/XVLMobileWaterLitR   :1035-1036
```

The input is litter C. `VLitR_col/AREA` is the dry litter depth in m, so `SoiSurfRoughness` is the hard-coded ground roughness (section 5), plus a particle-size term from surface-layer texture and organic content, plus the litter depth. More litter means a rougher surface and a slower overland flow, since the velocity is inversely proportional to `SoiSurfRoughness`; per unit C, woody litter adds half the volume of fine or manure litter. `SoiSurfRoughness` is set every hour for every column, before and independent of the erosion-mode test that follows it (`Hour1Mod.F90:924`). `SurfLitterC_col` is not the history field `Surf_LitrC_col`: that field reports `SoilOrgM_vr(ielmc,0)/AREA` (`f90src/IOutils/HistData/HistUpdateColumn.F90:192`, registered at `HistRegisterColumn.F90:475`), which `LitterLayerSummary` sets from `sumLitrOMLayL` (`RedistMod.F90:690-693`) and which also counts the litter-layer autotroph biomass (`MicrobialDiagMod.F90:201-210`, `sumLitrOMLayL`), whereas `sumSurfOMCK` returns autotroph C separately as `RC0ff_col` (`:403-410`). The two track each other but are not the same sum.

Other writers of `VLitR_col`: start-up sets it from the initial litter C, `VLitR0*ppmc*AREA` with `VLitR0 = sum_K RSC_vr(K,0)/BulkDensLitR(K)` (`f90src/Ecosim_mods/StartsMod.F90:890-895`, `InitLayerDepths`), and tillage scales it by the unmixed fraction `XCORP0 = AMAX1(0.001, XTillCorp_col)` (`f90src/Balances/TillageMixMod.F90:75`, `:208`, `ApplyTillageMixing`). The tillage call runs inside `UpdateOutputVars` (`RedistMod.F90:149` -> `:252`), after `LitterLayerSummary` (`:137`) has already formed that hour's `SurfLitterC_col`, so the next `UpdateLiterPropertz` overwrites the scaled value with one built from pre-tillage litter, and the tilled litter reaches `VLitR_col` one hour after that.

Where the runoff goes: `SurfRunoffPotentM_col` is routed between grid cells (`XGridsSurfRunoffM`, `SurfLitterPhysMod.F90:806-851`) and out of boundary faces (`XBoundSurfaceRunoffM`, `SurfPhysMod.F90:1324`), the latter only where the runoff flag and the boundary recharge factor allow it (`f90src/HydroTherm/SoilPhys/WatsubMod.F90:956-962`, `XBoundaryFlowM`); it carries solutes (`f90src/Transport/Nonsalt/TranspNoSaltSlowMod.F90:1639-1642`, `TracerFlowThruSurRofM`) and, when `iErosionMode` enables erosion (`f90src/Disturbances/ErosionMod.F90:75`, `erosion`), sets the sediment transport rate (`:198`, `OverLandFlowSedTransp`), while `RunoffVelocityM_col` sets detachment by flow (`:152`, `SedimentDetachmentM`). So the litter volume does reach overland flow, but only in hours with mobile water above the surface storage capacity `VWatStoreCapSurf_col`.

Ground energy outputs (`HistUpdateColumn.F90:232-240`): `SOIL_RN_col` (`HeatByRad2Surf_col`), `SOIL_LE_col` (`HeatEvapAir2Surf_col`), `SOIL_H_col` (`HeatSensAir2Surf_col`), `SOIL_G_col = -(HeatNet2Surf_col - HeatSensVapAir2Surf_col)`, `ECO_Radnet_col`, `ECO_LE_col`, `ECO_HeatS_col`, `ECO_Heat2G_col`. The ground sums are built per iteration in `AccumWaterVaporHeatFluxesM` (`SurfPhysMod.F90:1083-1090`) and, for litter, in `SurfLitREnergyBalanceM` (`SurfLitterPhysMod.F90:172-177`).

## Calibration parameters: source map

This page owns no plant or microbial file parameter as a hydrothermal lever. The file parameters below are the ones that genuinely reach ET or ground radiation; RSMX, RCS and OSMO are owned by the plant photosynthesis and stomatal page, where their photosynthesis uses are mapped.

| file name | Fortran variable | read at (file:line, subroutine) | every use site at cb243228 (subroutine, file:line, branch) | what it does (the equation, quoted) |
|---|---|---|---|---|
| RSMX | `CuticleResist_pft` -> `H2OCuticleResist_pft`, `CO2CuticleResist_pft` | `f90src/IOutils/PlantInfoMod.F90:1813` (`ReadPlantTraitTable`, live); copied `:815` (`SetPlantTraits`); `:643` (`ReadPlantTraitsNC`) is dead code | `InitShootGrowth`, `StartqMod.F90:176-177` and `InitPlantMod.F90:189-190`; `CalcStomataResist4H2O`, `PlantMathFuncMod.F90:570`; `StomatalDynamics`, `StomatesMod.F90:275`; `PhotoActivePFT`, `StomatesMod.F90:1062`, `:1065`; all branches (C3 and C4) | `H2OCuticleResist_pft = CuticleResist_pft/3600`; `Stomata_Resist = CanopyMinStomaResistH2O + (H2OCuticleResist - CanopyMinStomaResistH2O)*Stomata_Stress`; closed-stomata ceiling of the transpiration resistance in `Transpiration_pft = EX*Rb/(Rb+Rs)` |
| RCS | `RCS_pft` | `PlantInfoMod.F90:1812` (`ReadPlantTraitTable`); copied `:814` (`SetPlantTraits`) | `CalcStomataResist4H2O`, `PlantMathFuncMod.F90:569`; `StagePlantForGrowth`, `GrosubsMod.F90:554`; all branches | `Stomata_Stress = EXP(-PSICanopyTurg_pft(NZ)/RCS_pft(NZ))` |
| OSMO | `OrganOsmoPsi0pt_pft` | `PlantInfoMod.F90:1811` (`ReadPlantTraitTable`, into `CanOsmoPsi0pt_tab`); copied `:813` | `update_osmo_turg_pressure` calls in `CanopyEnergyH2OIter_func` (`UptakesMod.F90:832`, `:1141`), `HandlingDivergence` (`:624`, `:640`), `HandleBareSoil` (`:1430`, `:1449`), `UpdatePlantWaterVars` (`:1557`); initialisation `StartqMod.F90:152`, `:819`, `InitPlantMod.F90:971`, `:1050` | `PSIOsmo = FDMP*(OSMO/FDMP0 - RGASC*TKP*CCPOLT/OSWT)`, `PSITurg = AZMAX1(PSIOrgan - PSIOsmo)` (`PlantMathFuncMod.F90:71-72`) |
| IGTYP | `iPlantRootProfile_pft` | `PlantInfoMod.F90:1724` (`ReadPlantTraitTable`); copied `:715` | `CanopyInterceptPrecip`, `CanopyHydroMod.F90:57` (plus root-profile uses outside this topic) | `CanopyWatHeldCap = FoliarWatRetcap(iPlantRootProfile_pft)*LeafStalkAreaAct_pft`, classes 0/1/2 give 5.0E-4/2.5E-4/2.5E-4 |
| ISNTYP | `iPlantSnowIntercepType_pft` | `PlantInfoMod.F90:1745` (`ReadPlantTraitTable`); copied `:741` | `CanopyInterceptPrecip`, `CanopyHydroMod.F90:58`, `:80`, `:81` | `CanopySnowHeldCap = FoliarSnowRetcap(iPlantSnowIntercepType_pft)*LeafStalkAreaAct_pft`; `BulkFactor4Snow_pft = BulkFactor4Snow(class)` |
| ALBS (grid file) | `SoilAlbedo_col` | `f90src/IOutils/readimod.F90:440` (`readTopoNC`); copied `:553` | `SoilSRFEnerbyBalanceM`, `SurfPhysMod.F90:525`, `:529`; `InitAccumulators`, `StartsMod.F90:833` (to `SurfAlbedo_col`); `PlantAPICanMSend`, `PlantCanAPI.F90:123` -> `RadiationAtGround`, `SurfaceRadiationMod.F90:1355`, `:1362` | `AlbedoGrnd = (SoilAlbedo*VLSoilMicPMass + 0.06*VLWatGrnd + 0.30*VLIceGrnd)/(...)`; canopy model `GrndAlbedo = AMIN1(SurfAlbedo_col, SoilAlbedo + AZMAX1(SurfAlbedo_col-THETW1))`, which equals ALBS |

Hard-coded, with no file lever: ground roughness 0.020 m and `ZW = 0.01 m`, litter bulk densities `BulkDensLitR = (0.0333, 0.0167, 0.0167)` Mg m-3 and the coefficients of the particle-size roughness `ZD50` (section 10.1), emissivities 0.97, litter albedo 0.20, water/ice albedos 0.06/0.30, snow albedo 0.85, `RZ = ResistLeafSurf = 0.0139` h/m, `RAM = 1.39E-3` h/m, litter vapour diffusivity 7.70E-2 m2/h, interception capacities, unloading constants.
