---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/HydroTherm/SoilPhys/`, `f90src/HydroTherm/PhysData/SoilPhysParaMod.F90`, `f90src/HydroTherm/PhysData/PhysPars.F90`
**Last verified:** 2026-10-15
---

# Subsurface water and heat

This page covers the soil column: retention and conductivity, the `watsub` iteration with its Darcy, macropore, vapour and heat kernels, the exchange of root water with the soil, freeze-thaw, boundary drainage and the water table. See [index.md](index.md) for the hourly order and [surface_energy_balance_and_snow.md](surface_energy_balance_and_snow.md) for the surface boundary.

## 1. Water potentials

`GetSoilHydraulicVars` (`f90src/HydroTherm/SoilPhys/SoilHydroParaMod.F90:45-127`), called each hour from `hour1` (`f90src/Modelforc/Hour1Mod.F90:188`), sets per layer:

```
PSISoilMatricP_vr  = ComputePsiMCM(theta)            soil layers                               :75-78
PSISoilMatricP_vr  = ComputePSIPond(...)              pond/ice layers without soil mass         :81-82
PSISoilOsmotic_vr  = -RGASC*TKS_vr*SolutesIonConc_vr*1E-6                                       :92
PSIGrav_vr         = mGravAccelerat*(ALT_col - SoilDepthMidLay_vr)                               :93
ElvAdjstedSoilH2OPSIMPa_vr = min(0, matric + osmotic + gravitational)                            :94
HYCDMicP4RootUptake_vr = 0.5*(HydroCond_3D(1,K,L) + HydroCond_3D(3,K,L)),  K = getMoistK(THETW,POROS)   :122-123
```

`HYCDMicP4RootUptake_vr` is the soil conductivity the root model uses for the soil side of the soil-root resistance (`f90src/Plant_bgc/UptakesMod.F90:1280`, `CalcPlantHydroResistance`; see [../plant_bgc/roots_and_uptake.md](../plant_bgc/roots_and_uptake.md#7-root-hydraulics)). The same routine computes the soil bulk modulus used for root penetration (Grant 1993 Eq. 8, fitted to Rickman et al. 1992; `:98-116`).

### 1.1 Retention curve

`ComputePsiMCM` (`f90src/HydroTherm/PhysData/SoilPhysParaMod.F90:264-288`) is a piecewise log-log curve anchored at field capacity, wilting point and porosity:

```
theta < FC:            PSI = max(PSIHY, -exp(LOGPSIFLD + (log FC - log theta)/FCD * LOGPSIMND))          :275-278
FC <= theta < POROS-DTHETW:  PSI = -exp(LOGPSIAtSat + ((log POROS - log theta)/PSD)**SRP * LOGPSIMXD)   :279-281
otherwise:             theta = POROS, PSI = PSISE                                                       :282-285
```

with `FCD = log FC - log WP`, `PSD = log POROS - log FC` (`SoilHydroParaMod.F90:166-169`, `SoilHydroProperty`; or `:360-363`, `SetColdRunSoilStates`), `LOGPSIAtSat = log(-PSIPS)` with `PSIPS = -0.5E-3 MPa` (`f90src/Utils/EcoSimConst.F90:26`), `LOGPSIFLD = log(-PSIAtFldCapacity_col)`, `LOGPSIMN = log(-PSIAtWiltPoint_col)`, `LOGPSIMXD = LOGPSIFLD - LOGPSIAtSat`, `LOGPSIMND = LOGPSIMN - LOGPSIFLD` (`f90src/Ecosim_mods/StartsMod.F90:164-168`, `starts`; also `:1104-1105`, `startsim`). `PSIAtFldCapacity_col` and `PSIAtWiltPoint_col` are the grid-file PSIFC and PSIWP (`f90src/IOutils/readimod.F90:438-439`, `readTopoNC`), reset to -0.033 and -1.5 MPa for any layer whose FC or WP is entered as negative (`SoilHydroParaMod.F90:477-488`, `ComputeSoilHydroPars`).

**The wet-branch exponent `SRP_vr` is 0.67 for every layer.** `SoilHydroProperty` first sets 0.25 (organic, `CSoilOrgM > FORGC`), 0.33 (semi-organic) or 1.00 (mineral) (`SoilHydroParaMod.F90:148-155`) and then overwrites it, `if (zm_ecosys_retention) SRP_vr = 0.67` (`:158`), where `zm_ecosys_retention = .true.` is a compile-time parameter (`:34`) documented in source as an "ECOSIM_ZM" emulation of legacy ecosys `hour1.f`. The 0.25/0.33/1.00 branch is dead unless the parameter is changed and the model rebuilt.

**Ponds and ice.** `ComputePSIPond` (`SoilPhysParaMod.F90:84-126`) replaces FC and WP by `FCI*ice` and `WPI*ice` (`FCI = 0.05`, `WPI = 0.025`, `PhysPars.F90:29-30`); with no liquid water it returns the ice potential `PSI = LtHeatIceMelt*(TKS - TFice)/TFice` (`:107-113`) and aborts if no temperature is passed.

**Defaults when the soil file gives no FC or WP** (`SetColdRunSoilStates`, `SoilHydroParaMod.F90:318-413`; `FORGW = 0.25E6` gC/Mg at `:29`). A negative FC, WP, SCNV or SCNH in the grid file is a sentinel: `ComputeSoilHydroPars` marks that layer's property `isoi_unset` (`SoilHydroParaMod.F90:476-503`). On a cold start `SoilHydroProperty` keeps the file's FC and WP only when **both** are set (`:163`); if either is unset it calls `SetColdRunSoilStates`, which recomputes **both** (`:324`, "when either field capacity or wilting point is not provided, both are recomputed"). So a positive WP in the file is discarded in every layer whose FC is the sentinel, and the reverse. On a restart (`.not.is_cold_run()`) the stored FC and WP are used as they are (`:163`). `SoilHydroProperty` runs from `SetSoilPropertyAftDisturb` (`f90src/Modelforc/Hour1Mod.F90:550`) whenever `iResetSoilProf_col` is set: at initialisation (`f90src/Ecosim_mods/StartsMod.F90:770`, `InitAccumulators`) and after tillage, SOM removal or a soil-grid update. Sand and silt are read in kg Mg-1, clay is `1000 - (sand + silt)` (`f90src/IOutils/readimod.F90:785`, `readTopoNC`), and all three are converted to mineral-mass fractions by `1.0E-3*(1 - organic volume fraction)` (`:795-799`).

```
mineral (C < FORGW):  FC = 0.2576 - 0.20*sand + 0.36*clay + 0.60E-6*C        :329-330
                      WP = 0.0260 + 0.50*clay + 0.32E-6*C                     :345
organic:              FC = 0.27 / 0.62 / 0.71 and WP = 0.04 / 0.15 / 0.22 for bulk density < 0.075 / < 0.195 / otherwise   :333-339, :348-354
both:                 FC = min(0.75*POROS, FC/(1-macropore fraction)); WP = min(0.75*FC, WP/(1-macropore fraction))       :341-342, :356-357
```

The air-dry content `SoilWatAirDry_vr` is the theta at `PSIHY` on the dry branch (`:192-197`).

### 1.2 Conductivity table K(theta)

`SoilHydroProperty` (`SoilHydroParaMod.F90:132-315`), called from `hour1` when soil properties change (`Hour1Mod.F90:550`), builds a 100-bin table by the Green and Corey (1971, Eq. 1 and Table 1 II) integration over the retention curve (`:236-289`):

```
H2OSOIK(K) = POROS*(1 - (K-1)/100),  PSISK(K) = ComputePsiMCM(H2OSOIK(K))      :240-243
SUM2 = sum_K (2K-1)/PSISK(K)^2                                                  :244
YK = (1 - (K-1)/100)**1.33;  SUM1 = sum_{M>=K} (2(M-K)+1)/PSISK(M)^2            :254-258
HydroCond_3D(3,K,L) = SatHydroCondVert_vr*YK*SUM1/SUM2     vertical             :263
HydroCond_3D(1:2,K,L) = SatHydroCondHrzn_vr*YK*SUM1/SUM2   lateral              :286
```

`getMoistK(theta, POROS) = max(1, min(100, 101 - int(100*theta/POROS)))` maps water content to a bin (`SoilPhysParaMod.F90:291-298`); bin 1 is saturation. Because the table is built from the retention curve, the `SRP = 0.67` override also changes K(theta).

**Air entry.** With `zm_ecosys_airentry = .true.` (`SoilHydroParaMod.F90:35`) the air-entry potential and saturated content are defined where vertical conductivity first drops below 0.1 of `SatHydroCondVert_vr`: `PSISoilAirEntry_vr = PSISK(K-1)`, `ThetaSat_vr = H2OSOIK(K-1)` (`:266-276`; the same rule for litter in `LitterHydroproperty`, `:450-458`). These two values switch `MicropXGridDarcyFlow` between saturated and Green-Ampt regimes (§3.1).

**Saturated conductivity defaults** when the soil file leaves Ksat unset (`:204-226`): mineral `Ksat = 1.54*((POROS - THETF)/THETF)**2`, with `THETF` the content at -0.033 MPa on the wet branch; organic `Ksat = (0.10 + 75*1E-15**BulkDensity)*FracSoiAsMicP_vr`.

**Macropores** are Poiseuille pipes of radius 0.5 mm (Dimitrov et al. 2010 Eq. 3.3-3.4; `:301-312`): `MacPoreNumbers = int(VLMacP/(pi*r^2*VGeomLayert0))`, `HydroCondMacP_vr = 3.6E3*pi*MacPoreNumbers*r^4/(8*Viscosity_H2O(T))`. Each hour the effective macropore conductivity scales with the square of the ice-free macropore fraction, `HydroCondMacP1_vr = HydroCondMacP_vr*rsatMacP**2` (`WatsubMod.F90:509-516`, `LocalCopySoilVars`; `:1334-1340`, `UpdateSoilMoistTempM`).

## 2. Thermal conductivity and freezing point

`CalcSoilThermConductivity` (`SoilPhysParaMod.F90:211-244`) is a de Vries-type weighted mean with a Rayleigh-Nusselt convective enhancement above threshold water and air contents (`TRBW = 0.375`, `TRBA = 0`, `PhysPars.F90:27-28`):

```
XNUSW1 = max(1, 0.68 + 0.67*RYLNW1**0.25/DNUSW),  RYLNW1 = min(1E4, RYLXW*DTKX*max(0,thetaW-TRBW)**3*1E-6)   :226-232
TCND1 = (NumerSolid + thetaW*2.067E-3*XNUSW1 + 0.611*thetaI*7.844E-3 + WTHET1*thetaA*9.050E-5*XNUSA1)
      / (DenomSolid + thetaW + 0.611*thetaI + WTHET1*thetaA),  WTHET1 = 1.467 - 0.467*FracSoilAsAirt        :236-240
```

The litter conductivity uses the same form with organic, water and ice weights 0.779, 0.622, 0.380 (`f90src/HydroTherm/SurfPhys/SurfLitterPhysMod.F90:186-215`).

`get_Tfrez` (`SoilPhysParaMod.F90:247-260`) is the Clausius-Clapeyron freezing point after Cary and Mayland (1972): `TFREEZ = -9.0959E4/(max(PSI, -5.5) - LtHeatIceMelt)`.

## 3. The watsub iteration and the internal 3-D fluxes

`watsub` (`f90src/HydroTherm/SoilPhys/WatsubMod.F90:86-210`) is outlined in [index.md](index.md#the-watsub-iteration). Before the loop, `LocalCopySoilVars` copies water, ice, air and heat capacities into iteration arrays and identifies the subsurface-irrigation layer (`:381-550`); `InitSoilHydrauics` converts last hour's root water exchange into a per-iteration amount `dWaterPlantRoot2SoilPrev_vr = TWaterPlantRoot2SoilPrev_vr*dts_HeatWatTP` (`:572-574`) and builds the harmonic-mean macropore conductance `AVCNHL_3D` between neighbouring cells (`:613-619`).

`Subsurface3DInternalFlowM` (`:628-792`) sweeps west to east, north to south and top to bottom, visiting each interface once (`:667-698`), skips empty layers by searching down for the next layer with pore space (`:702-707`), and for each valid pair calls (`:728-762`):

1. `CalcSoilWatPotential` for both cells (`SoilPhysParaMod.F90:35-81`);
2. `MicropXGridDarcyFlow` (`WatsubMod.F90:1861-2065`);
3. `MacropXgridFLow` (`:2067-2139`);
4. `WaterVaporXgridFlow` (`:2142-2207`);
5. `SolveXgridHeatConduction` (`:2210-2312`).

The per-iteration results go to `WaterFlow2Micpt_3D`, `WaterFlow2Macpt_3D`, `HeatFlow2Soili_3D` and are stored by iteration in `WaterFlow2MicPM_3D(M,...)`, `WaterFlow2MacPM_3D(M,...)` for transport (`:754-779`); for vertical pairs the water-film thickness is updated (`:781-783`).

### 3.1 Micropore Darcy flow

Four regimes by whether each cell's matric potential is above its air-entry potential (`:1895-1957`): both saturated, source saturated (destination content from the wetting-front volume `VLWatMicPX1_vr`, potential recomputed), destination saturated (mirror), both unsaturated. Then:

```
HydCondSrc = HydroCond_3D(N,K1,src) * RainEkReducedKsat  (top layer only)       :1964-1968
PSIST = PSISM1 + PSIGrav + PSISoilOsmotic                                         :1979, :1983
AVE_CONDUCTANCE = 2*Ksrc*Kdst/(Ksrc*DLYR_dst + Kdst*DLYR_src)                     :1994-1998
PtWatDarcyFlux  = AVE_CONDUCTANCE*(PSIST1 - PSISTL)*AREA*dts_HeatWatTP            :2009
WatDarcyFlowMicP = max(0, min(PredDarcyFlow, VLWatMicP2(src)*dts_wat, VLairMicP1(dst)*dts_wat))   forward  :2022
```

with mirror limits for reverse flow (`:2039`), excess-over-saturation drainage added when a cell is above `ThetaSat_vr` (`:2014-2020`, `:2032-2037`), and an overfull vertical destination pushing water back (`:2048-2052`). Heat is advected upwind, `cpw*T*Q*HeatAdv_scal` (`:2055-2060`). All flow is skipped when `fixWaterLevel` (`:1890`). The scheme is explicit, first-order and flux-limited; there is no tridiagonal solve.

### 3.2 Macropore, vapour and conductive heat flow

- **Macropores** (`:2089-2137`): potential `PSIGrav + g*DLYR*(min(1, water/volume) - 0.5)` in each cell (`:2091-2094`), flux `AVCNHL_3D*(PSISH1-PSISHL)*AREA*dts_HeatWatTP` (`:2104`) limited by water and air space; vertical flow is downward only (`:2118-2119`). Disabled by `LMacPoreOff` (`:747`, `:2089`).
- **Vapour** (`:2177-2205`), when both cells exceed `AirFillPore_Min = 1E-3` (`EcoSimConst.F90:44`): Kelvin vapour pressures `vapsat(T)*exp(18*PSISV/(RGASC*T))`, conductances `WVapDifusvitySoil*thetaA^2*POROQ/POROS` combined harmonically, limited by the equilibrium vapour content and available water; the heat carried is `(cpw*T + EvapLHTC)*flux`. `WVapDifusvitySoil_vr = WGSG*TEFGASDIF(T)` with `WGSG = 7.70E-2` m2/h (`Hour1Mod.F90:1327`; `f90src/Modelpars/ChemTracerParsMod.F90:30`).
- **Conduction** (`:2236-2310`): conductivities from `CalcSoilThermConductivity` for both cells (`:2239-2241`), harmonic `ATCNDL` (`:2243`); the top layer's temperature is first shifted by the surface flux `HeatFluxAir2Soi` when it is not under snow (`:2260-2262`); the conductive flux `HFLWC = ATCNDL*(TK1X-TKLX)*AREA*dts_HeatWatTP` is capped by the heat that would bring both cells to their common temperature (`:2300-2308`).

## 4. Layer update, root water and surface coupling

`UpdateSoilMoistTempM` (`WatsubMod.F90:1262-1446`) adds the net micropore and macropore flows, macropore-micropore exchange, thaw and irrigation (`:1290-1300`), recomputes air volumes, pore fractions and macropore conductivity (`:1304-1341`) and heat capacities (`:1346-1352`), and then applies the root water exchange:

```
VLWatMicP1t = VLWatMicP1 + dWaterPlantRoot2SoilPrev_vr                                 :1356
if (VLWatMicP1t < 0 and VLWatMicP1 > 0):  pscal = -VLWatMicP1/dWaterPlantRoot2SoilPrev_vr,
     unsupplied part written back to TWaterPlantRoot2SoilPrev_vr                       :1358-1361
```

`dWaterPlantRoot2SoilPrev_vr` is negative for uptake and comes from the previous hour's `RootUptakes` (copied at `Hour1Mod.F90:862`, `SetArrays4PlantSoilTransfer`), so soil water is withdrawn one hour after the transpiration it supplied is booked in `ECO_ET_col`.

The new temperature is energy-conserving and, for the top layer, semi-implicit in the surface long-wave and sensible terms through `dHGrnddTKsoi1 = -4*LWEmscefSoil*TKSoil1^3 - CdSoiHSens_col` (`SurfPhys/SurfPhysMod.F90:1653`):

```
TKSoil1(top) = (ENGY1 + THeatFlow2Soil_3DM + HeatIrrigation1 + TLPhaseChangeHeat2Soi1
                + dHeatPlantRoot2SoilPrev - dHGrnddTKsoi1*TKSoil1) / (VHeatCapacity1 - dHGrnddTKsoi1)      :1376-1378, :1385-1387
TKSoil1(other) = (ENGY1 + THeatFlow2Soil_3DM + HeatIrrigation1 + TLPhaseChangeHeat2Soi1 [+ root heat]) / VHeatCapacity1   :1380-1381, :1389-1390
```

Root heat enters only when the root releases water to the soil (`:1373-1382`). Soil-cable warming nudges warming layers toward `TKS_ref_vr` (`:1410-1418`), and temperatures above 400 K abort (`:1420-1426`).

## 5. Freeze-thaw

`FreezeThawIterateM` (`WatsubMod.F90:2552-2688`) is called from `Summarize3DFlowM` for every layer and iteration (`:1185`). It computes the apparent temperature after this iteration's heat and water fluxes, then latent-heat-limited phase change for macropores and micropores separately, **both at the depressed freezing point**:

```
PSISMX = PSISoilMatricPtmp_vr + PSISoilOsmotic_vr;  TFREEZ = get_Tfrez(PSISMX)                  :2600-2602
TK1App = (VHeatCapacity1*TKSoil1 + THeatFlow2Soil_3DM + HeatIrrigation1)/VLHeatCapacityX        :2606-2611
MacPIceHeatFlxFrezPt = (cpw*VLWatMacP1X + cpi*VLiceMacP1)*(TFREEZ - TK1App)/(1 + 6.2913E-3*(TFREEZ - TFICE))*dts_wat   :2621-2623
MicPIceHeatFlxFrezPt = VLHeatCapacityAX*(TFREEZ - TK1App)/(1 + 6.2913E-3*(TFREEZ - TFice))*dts_wat                   :2644-2646
thaw:   max(-LtHeatIceMelt*DENSICE*ice*dts_wat, Pt);   freeze: min(LtHeatIceMelt*water*dts_wat, Pt)                   :2627-2631, :2649-2654
FIceThawed = -heat/LtHeatIceMelt                                                                                     :2633, :2655
```

`dcpo`, the root organic-matter heat capacity, is added only with `plantOM4Heat` (`:2594-2599`, `:2610`, `:2645`). Totals accumulate into `TLIceThawMicP_vr`, `TLIceThawMacP_vr`, `TLPhaseChangeHeat2Soi_vr` (`:2680-2685`). Unfrozen water in frozen soil exists because micropore water freezes only below `TFREEZ`. After the hourly loop, `watsub` sets `NLF_col` to the shallowest layer with ice fraction above 0.9 (`:184-187`); the index is never reset, and it bounds ebullition in transport (see [../transport/gas_transport.md](../transport/gas_transport.md#5-ebullition)).

## 6. Boundaries, drainage and the water table

`XBoundaryFlowM` (`WatsubMod.F90:795-1051`) handles each column's external faces. Per layer it decides whether micropore and macropore water may discharge to the external water table (`Config4WaterTableDrain`, `:841`) and to tile drains (`Config4TileDrainage`, `:843`; `:1598-1670`), handles surface runoff out of boundary faces (`XBoundSurfaceRunoffM`, `:962`), and then:

- **No water table, or the vertical face** (`:974-976`): `VertBoundaryDrainM` (`:1193-1259`) drains by gravity on the slope, `WaterFlow2Micpt = AZERO(min(VOLWZ, max(-VOLWZ, RechargRate*HydGrad*HydcondSrc)))` with `RechargRate = Recharg2WTBLScal*dts_HeatWatTP*RechargDist2WTBL` and `HydGrad = XN*g*(-|SLOPE|)*AREA` (`:1215`, `:1229-1233`); the same form for macropores (`:1237`), both bounded by the cell's water.
- **With a water table, lateral faces** (`:979-995`): discharge to the external water table (`DischargeOverWaterTBL`, `:983-985`), tile discharge (`:990-991`) and recharge from the water table (`RechargeFromExtWaterTBL`, `:994-995`).

`DischargeOverWaterTBL` (`:2314-2450`): micropore head `PSISWT = min(0, -PSISM - 0.03*PSIO + g*(z_mid - TargetWaterTBL - max(0, z_mid - DepzIntWTBL)))`, slope term added when negative (`:2363-2382`), flux `PSISWT*outlet_conductivity*AREA*(1-FracLayVolBelowWTBL)/(RechargDist2WTBL+1)*Recharg2WTBLScal*dts_HeatWatTP` (`:2384-2385`); macropores analogously (`:2420-2448`). `RechargeFromExtWaterTBL` (`:2453-2549`) adds water to layers below the water table and inside the active layer when they have air space (`:2480-2519`; macropores `:2523-2547`).

**Legacy-ecosys outlet (compile-time, on).** `zm_ecosys_outlet = .true.` (`WatsubMod.F90:62`) changes only the external water-table path: micropore discharge is enabled only where the matric potential exceeds `ZmOutletWetnessPotential`, the potential at which vertical K first drops below 0.1 Ksat, and every deeper layer above the water table and inside the active layer also meets it (`Config4WaterTableDrain`, `:1689-1711`; `ZmOutletWetnessPotential`, `:1767-1790`); the head is referenced to the air-entry potential and the outlet conductivity follows the current moisture bin instead of bin 1 (`:2369-2380`; macropore head `:2424-2428`). The upstream gating (`:1724-1763`) is skipped. Tile drainage is unchanged. The source comment states this is not a seepage-face implementation.

## 7. Numerical scheme summary

| Aspect | EcoSIM choice at cb243228 |
|---|---|
| Retention | Piecewise log-log on FC, WP, porosity; wet-branch exponent `SRP = 0.67` everywhere (compile-time override) |
| Unsaturated K(theta) | Green-Corey integration over 100 bins, table `HydroCond_3D` |
| Air entry / saturation | Where vertical K < 0.1 Ksat (compile-time `zm_ecosys_airentry`) |
| Saturated K | Soil file, or texture/organic defaults |
| Macropore K | Poiseuille, r = 0.5 mm, scaled by (ice-free fraction)^2 |
| Richards solver | Explicit, first-order upwind, `NPH` iterations per hour, flux limiters, no tridiagonal solve |
| Vapour | Kelvin vapour pressure, Millington-type tortuosity `thetaA^2*POROQ/POROS` |
| Heat | Explicit conduction (de Vries with convective Nusselt factor) plus upwind advection; top layer semi-implicit in long-wave and sensible heat |
| Phase change | Explicit, latent-heat limited, Clausius-Clapeyron depression for micropores and macropores |
| Root water | Previous hour's uptake withdrawn per iteration, scaled to keep layers non-negative |
| External water table | Legacy-ecosys outlet gate and conductivity (compile-time `zm_ecosys_outlet`) |

## Calibration parameters: source map

No plant or microbial file parameter enters the soil water and heat solver directly; the plant link is the root water flux (§4). The grid-file parameters that set the retention curve are mapped here. The grid surface is indexed in the knowledge graph (category `soil_and_site`, mechanism `Soil_Water_Retention_Derivation`), its names and descriptions taken from the model's own example grid file.

| file name | Fortran variable | read at (file:line, subroutine) | every use site at cb243228 (subroutine, file:line, branch) | what it does (the equation, quoted) |
|---|---|---|---|---|
| PSIFC (grid) | `PSIAtFldCapacity_col` | `f90src/IOutils/readimod.F90:438` (`readTopoNC`) | `starts`, `f90src/Ecosim_mods/StartsMod.F90:165`; `startsim`, `:1104`; overwritten to -0.033 by `ComputeSoilHydroPars` (`SoilHydroParaMod.F90:480`) for layers with negative FC; ATS path `ATSEcoSIMAdvanceMod.F90:300` | `LOGPSIFLD_col = LOG(-PSIAtFldCapacity_col)`; anchors both retention branches and `LOGPSIMXD`, `LOGPSIMND` |
| PSIWP (grid) | `PSIAtWiltPoint_col` | `readimod.F90:439` (`readTopoNC`) | `starts`, `StartsMod.F90:166`; `startsim`, `:1105`; overwritten to -1.5 at `SoilHydroParaMod.F90:488` for layers with negative WP | `LOGPSIMN_col = LOG(-PSIAtWiltPoint_col)`; `LOGPSIMND_col = LOGPSIMN_col - LOGPSIFLD_col` sets the dry-branch slope |

Hard-coded, with no file lever: `SRP = 0.67`, the 0.1 Ksat air-entry rule, macropore radius 0.5 mm, the convective thresholds `TRBW`, `TRBA`, the pedotransfer coefficients, `PSIPS = -0.5E-3` MPa, `FCI`, `WPI`, the outlet rule.
