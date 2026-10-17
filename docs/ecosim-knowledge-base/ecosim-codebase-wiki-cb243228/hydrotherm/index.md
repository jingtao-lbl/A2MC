---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/HydroTherm/` (all subdirectories), with the canopy energy-water solver in `f90src/Plant_bgc/UptakesMod.F90` and the ET bookkeeping in `f90src/Balances/RedistMod.F90`
**Last verified:** 2026-10-15
---

# HydroTherm subsystem

`f90src/HydroTherm/` holds EcoSIM's water and energy balance for the column below the canopy: canopy interception of rain and snow, partitioning of radiation and turbulent fluxes over snow, litter and bare soil, the layered snowpack, 3-D soil water and heat flow, freeze-thaw and water-table exchange. The canopy's own energy balance (transpiration, interception evaporation, canopy temperature) is solved in `Plant_bgc/UptakesMod.F90` and is documented here too, because it produces the largest term of evapotranspiration (`ECO_ET_col`).

Pages:

- [surface_energy_balance_and_snow.md](surface_energy_balance_and_snow.md): the `ECO_ET_col` producing equation and its decomposition, canopy interception and transpiration, aerodynamic resistances and ground roughness, the litter vapour-resistance chain, ground albedo and net radiation, the bare-soil and litter energy balances, the snowpack, and the chain from surface litter volume to surface roughness and overland flow (section 10.1).
- [subsurface_water_and_heat.md](subsurface_water_and_heat.md): retention and conductivity curves (with the compile-time `ECOSIM_ZM` overrides), the `watsub` iteration, Darcy, macropore and vapour flow, heat conduction, root-water exchange with the soil, freeze-thaw, boundary drainage and the water table.
- Root water uptake itself (soil-root resistances, the canopy water-potential iteration) is in [../plant_bgc/roots_and_uptake.md](../plant_bgc/roots_and_uptake.md) §7-§8; stomatal resistance is in the plant photosynthesis page.

## Source inventory at cb243228

| File (lines) | Main routines (header line) | Purpose |
|---|---|---|
| `CanopyPhys/CanopyHydroMod.F90` (103) | `CanopyInterceptPrecip` (`:25`) | Rain and snow interception per PFT, wind/temperature snow unloading, throughfall and its temperature (`:54-100`). |
| `PhysData/HydroThermData.F90` (190) | allocate/destroy | Iteration arrays and `HeatAdv_scal = 1` (`:61`), set to 0 when `fixWaterLevel` (`SoilPhys/WatsubMod.F90:116`). |
| `PhysData/PhysPars.F90` (49) | constants | `TRBA`, `TRBW` (`:27-28`), `FCI`, `WPI` (`:29-30`), `MinSnowDepth=0.075` (`:31`), `RAM=1.39E-03` h/m (`:32`), `RZ=0.0139` h/m (`:33`), Rayleigh/Nusselt groups (`:34-45`), `ZEROL=1E-3` (`:48`). |
| `PhysData/SoilPhysParaMod.F90` (310) | `CalcSoilWatPotential` (`:35`), `ComputePSIPond` (`:84`), `SetDeepSoil` (`:129`), `CalcSoilThermConductivity` (`:211`), `get_Tfrez` (`:247`), `ComputePsiMCM` (`:264`), `getMoistK` (`:291`) | Retention curve, thermal conductivity, freezing point. |
| `SnowPhys/SnowBalanceMod.F90` (848) | `SnowMassUpdate` (`:57`), `SnowpackDisapper` (`:170`), `DealHighTempSnow` (`:263`), `DealNegativeSnowMass` (`:309`), `UpdateSnowLayerL` (`:387`), `SnowpackLayering` (`:549`) | Hourly snow bookkeeping after transport (called from `Balances/RedistMod.F90:127`, `:145`). |
| `SnowPhys/SnowPhysMod.F90` (1930) | `InitSnowLayers` (`:56`), `SolveSnowpackM` (`:482`), `SnowAtmosExchangeMM` (`:765`), `CalcSnowBNDResistance` (`:1369`), `SnowSurLitterExch` (`:1720`), `SnowTopSoilExch` (`:1819`) | Snow energy balance, sublimation, layer solver, snow-litter-soil exchange. |
| `SnowPhys/SnowTransportMod.F90` (294) | `SaltPercolThruSnow` (`:39`), `DiagSnowChemMass` (`:186`), `SoluteTransportThruSnow` (`:257`) | Solutes in the snowpack. |
| `SoilPhys/SoilHydroParaMod.F90` (1045) | `GetSoilHydraulicVars` (`:45`), `SoilHydroProperty` (`:132`), `SetColdRunSoilStates` (`:318`), `LitterHydroproperty` (`:415`), `ComputeSoilHydroPars` (`:472`) | Potentials, K(theta) tables, default FC/WP/Ksat, geotechnical helpers (`:508-1044`). |
| `SoilPhys/WatsubMod.F90` (2690) | `watsub` (`:86`), `Subsurface3DInternalFlowM` (`:628`), `XBoundaryFlowM` (`:795`), `UpdateSoilMoistTempM` (`:1262`), `MicropXGridDarcyFlow` (`:1861`), `FreezeThawIterateM` (`:2552`) | The hourly water-heat driver and its kernels. |
| `SurfPhys/SurfPhysMod.F90` (1831) | `StageSurfacePhysModel` (`:114`), `SurfaceResistances` (`:355`), `SoilSRFEnerbyBalanceM` (`:447`), `InitSurfModelM` (`:1107`), `RunSurfacePhysModelM` (`:1601`) | Surface staging, resistances, bare-soil energy balance, infiltration and runoff. |
| `SurfPhys/SurfLitterPhysMod.F90` (886) | `PartLitSoilFractionM` (`:43`), `SurfLitREnergyBalanceM` (`:69`), `SurfLitterIterationM` (`:219`), `UpdateLitRBe4RunoffM` (`:558`), `XGridsSurfRunoffM` (`:741`) | Litter cover fraction, litter energy and vapour balance, overland flow. |
| `SurfPhys/SurfPhysData.F90` (134), `SurfPhys/SurfPhysAPI.F90` (13) | allocate/destroy; empty module | `SurfPhysAPI` (and `f90src/APIs/SurfPhysAPI.F90`) contain no code. |

## Where HydroTherm runs in the hour

The standalone model advances one hour in `Run_EcoSIM_one_step` (`drivers/ecosim/EcoSIMAPI.F90:37`). The order matters for ET:

```
hour1            (EcoSIMAPI.F90:49)   resets accumulators, soil potentials, canopy radiation,
                                      canopy-air forcing, canopy interception
WATSUB           (EcoSIMAPI.F90:56)   ground, litter and snow energy balance; soil water and heat
MicrobeModel     (EcoSIMAPI.F90:63)   if microbial_model
PlantModel       (EcoSIMAPI.F90:73)   RootUptakes -> canopy transpiration and evaporation, root uptake
soluteModel      (EcoSIMAPI.F90:82)   if soichem_model
TranspNoSalt     (EcoSIMAPI.F90:91)   gas and solute transport (../transport/index.md)
TranspSalt       (EcoSIMAPI.F90:100)  if salt_model
EROSION          (EcoSIMAPI.F90:110)
REDIST           (EcoSIMAPI.F90:117)  state update, ET accumulation into ECO_ET_col
```

`watsub` is the live path for every standalone run; an ATS-coupled build replaces it with `StageSurfacePhysModel`, `RunSurfacePhysModelM` and `UpdateSurfaceAtM` called from `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:303`, `:322`, `:336`.

Inside `hour1` (`f90src/Modelforc/Hour1Mod.F90:85-250`), for each column: soil matric, osmotic and gravitational potentials and the root-uptake conductivity (`GetSoilHydraulicVars`, `:188`); surface litter properties (`:195`); the canopy radiation model, which also computes the canopy roughness length, zero-plane displacement and the isothermal aerodynamic resistances (`PlantCanopyRadsModel`, `:201`); the hand-over of last hour's latent and sensible heat stores into `TLEX_col`, `TSHX_col` (`:210-214`); and canopy interception (`CanopyInterceptPrecip`, `:238`).

Three timing facts follow directly from this order:

1. **Ground fluxes see last hour's canopy.** The canopy-air vapour pressure and temperature used by the ground, litter and snow, `VPQ_col = VPA_col - TLEX_col/(EvapLHTC*AREA)` and `TKQ_col = TairK_col - TSHX_col/(SpecHeatCapAir*AREA)` (`SurfPhys/SurfPhysMod.F90:275-276`, `SetCanopyProperty`), are built from the previous hour's total latent and sensible flux times resistance, accumulated in `RootUptakes` for the canopy (`Plant_bgc/UptakesMod.F90:219-221`) and in `UpdateOutputVars` for the ground (`Balances/RedistMod.F90:221-222`).
2. **The canopy does not see canopy air.** Canopy transpiration and evaporation are driven by the reference-height forcing `VPA_col` and `TairK_col` (`f90src/APIs/PlantAPI4Uptake.F90:79`, `:84`; `Plant_bgc/UptakesMod.F90:857`, `CanopyEnergyH2OIter_func`), never by `VPQ_col` or `TKQ_col`.
3. **Root water leaves the soil one hour after the transpiration it supplies is booked.** Root uptake from hour h is copied into `TWaterPlantRoot2SoilPrev_vr` in hour h+1 (`Modelforc/Hour1Mod.F90:862`, `SetArrays4PlantSoilTransfer`) and withdrawn from each layer during that hour's `watsub` iterations (`SoilPhys/WatsubMod.F90:572`, `InitSoilHydrauics`; `:1356-1371`, `UpdateSoilMoistTempM`). The canopy water store absorbs the lag.

## The watsub iteration

`watsub` (`SoilPhys/WatsubMod.F90:86-210`) copies state into iteration arrays (`LocalCopySoilVars`, `:125`), stages the surface once per hour (`StageSurfacePhysModel`, `:130`), sets inter-layer macropore conductances and the per-iteration root-water fluxes (`InitSoilHydrauics`, `:132`), then loops `M = 1..NPH` (`:137`):

```
PrepHydroThermIterM           :141
RunSurfacePhysModelM          :143   snow, ground, litter energy balance; infiltration; runoff
CopySoilWatVolIterateM        :146
Subsurface3DInternalFlowM     :149   Darcy, macropore, vapour and heat between cells
XBoundaryFlowM                :151   boundary drainage, water table, lateral runoff
Summarize3DFlowM              :153   net fluxes; FreezeThawIterateM at :1185
AccumulateSnowRedisFluxM      :155   if snowRedist_model
UpdateSoilMoistTempM          :157   new water, ice, temperature per layer
AggregateSurfRunoffFluxM      :159
UpdateSurfaceAtM              :161
UpdateStateFluxAtM / UpdateFluxAtExit  :163-167
ExitMassBalanceM              :169
```

After the loop it sets `NLF_col` to the shallowest layer whose ice fraction exceeds 0.9 (`:184-187`; this index is never reset and controls ebullition, see [../transport/gas_transport.md](../transport/gas_transport.md)) and copies the iteration state back (`:191-196`).

Time steps (`f90src/Ecosim_mods/StartsMod.F90:963-978`, `set_ecosim_solver`): `dts_HeatWatTP = 0.99999/NPH`, `dts_wat = AMIN1(1, 10*dts_HeatWatTP)*0.99999`, `XNPR = 0.99999/NPR`, `XNPS = 0.99999/NPS`, `dts_sno = dts_wat*XNPS`. `NPH` and `NPT` come from the site file (`NPXS1`, `NPYS1`, `:960-961`); `NPR = NCYC_LITR` and `NPS = NCYC_SNOW` default to 20 (`drivers/ecosim/EcoSIMAPI.F90:204-205`, `readnamelist`).

## Evapotranspiration in one paragraph

`ECO_ET_col` [mm] is a year-to-date cumulative, `m2mm*QEvap_CumYr_col/AREA` (`f90src/IOutils/HistData/HistUpdateColumn.F90:213`, `update_hist_columns`; registered with avgflag `I` at `HistRegisterColumn.F90:560`), reset to zero on day 1 (`f90src/Modelforc/YearMod.F90:53`, `:68`, `SetAnnualAccumlators`). Each hour `HandleSurfaceBoundary` subtracts `VapXAir2GSurf_col + QVegET_col` (both positive into the surface) from `QEvap_CumYr_col` (`Balances/RedistMod.F90:408-410`). `VapXAir2GSurf_col` is bare-soil, snow and litter vapour exchange summed over the `NPH` iterations (`SurfPhys/SurfPhysMod.F90:1096`, `:1596`); `QVegET_col` is transpiration plus canopy evaporation and sublimation summed over active PFTs (`Plant_bgc/ExtractsMod.F90:398`). Dew and condensation enter with the opposite sign and reduce `ECO_ET_col`. The full decomposition with every producing equation is in [surface_energy_balance_and_snow.md](surface_energy_balance_and_snow.md#1-eco_et_col-producing-equation-and-decomposition).

## Compile-time and run-time switches that change the physics

| Switch | Value at cb243228 | Effect |
|---|---|---|
| `zm_ecosys_retention` | `.true.` parameter (`SoilPhys/SoilHydroParaMod.F90:34`) | Forces `SRP_vr = 0.67` for every layer (`:158`), overriding the 0.25/0.33/1.00 texture branch (`:148-155`). |
| `zm_ecosys_airentry` | `.true.` parameter (`SoilHydroParaMod.F90:35`) | Air-entry potential and saturation set where vertical K falls below 0.1 Ksat (`:266-276`; litter `:450-458`). |
| `zm_ecosys_outlet` | `.true.` parameter (`SoilPhys/WatsubMod.F90:62`) | Legacy-ecosys micropore discharge gate and outlet conductivity for the external water table (`:1689-1712`, `:2369-2380`). |
| `fixWaterLevel` | `.false.` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:78`) | When true: no Darcy, macropore or vapour flow, `HeatAdv_scal = 0`. |
| `LMacPoreOff` | `.false.` (`EcoSIMCtrlMod.F90:12`) | Turns macropore flow off (`WatsubMod.F90:747`, `:2089`). |
| `plantOM4Heat` | `.false.` (`EcoSIMCtrlMod.F90:77`) | Adds root organic matter to layer heat capacity (`WatsubMod.F90:494-497`, `:2594-2599`). |
| `snowRedist_model` | `.true.` (`EcoSIMCtrlMod.F90:73`) | Lateral snow redistribution (`SurfPhysMod.F90:1641`). |
| `mod_snow_albedo` | `.false.` (`EcoSIMCtrlMod.F90:81`) | When true, snow albedo comes from `SnowAlbedo_col` instead of the dry/ice/water mix (`SnowPhys/SnowPhysMod.F90:800-805`). |

The three `zm_ecosys_*` parameters are commented in source as an "ECOSIM_ZM" experiment emulating legacy ecosys; changing them requires a rebuild.

## What the previous wiki got wrong

Verified at cb243228; the full audit is `memory/dev_logs_adapterkit/ecosim_wiki_audit_cb243228/06_hydrotherm_transport.md` (dev repo only).

| Previous claim | Fact at cb243228 | Where |
|---|---|---|
| `watsub` is not called; the ATS coupler is the active path | `Run_EcoSIM_one_step` calls `WATSUB` every hour (`drivers/ecosim/EcoSIMAPI.F90:56`); ATS is used only in coupled builds | [above](#where-hydrotherm-runs-in-the-hour) |
| Canopy energy balance and stomata are built on canopy air `VPQ_col`, `TKQ_col` | The canopy uses `VPA_col`, `TairK_col`; only ground, litter and snow use `VPQ_col`, `TKQ_col` | [surface page §1.3](surface_energy_balance_and_snow.md#13-what-drives-which-term) |
| Retention exponent `SRP` = 0.25 / 0.33 / 1.00 by organic content | Overwritten to 0.67 everywhere by compile-time `zm_ecosys_retention` (`SoilPhys/SoilHydroParaMod.F90:158`) | [subsurface page §1.1](subsurface_water_and_heat.md#11-retention-curve) |
| Macropore water freezes at bulk `TFICE`; denominator `1 + 6.2913E-3*T` | Both pore classes freeze at the depressed `TFREEZ`; denominator `1 + 6.2913E-3*(TFREEZ - TFICE)` (`SoilPhys/WatsubMod.F90:2623`, `:2646`) | [subsurface page §5](subsurface_water_and_heat.md#5-freeze-thaw) |
| Snowfall is not intercepted | Snow is intercepted by ISNTYP class and unloaded by wind and warmth (`CanopyPhys/CanopyHydroMod.F90:58-79`) | [surface page §2](surface_energy_balance_and_snow.md#2-canopy-interception-of-rain-and-snow) |
| `FreezeThawIterateM` is called from `UpdateSoilMoistTempM` | Called from `Summarize3DFlowM` (`WatsubMod.F90:1185`) | [subsurface page §5](subsurface_water_and_heat.md#5-freeze-thaw) |
| `HYCDMicP4RootUptake_vr` is used in `NutUptakeMod` | Used in `CalcPlantHydroResistance` (`Plant_bgc/UptakesMod.F90:1280`) | [subsurface page §1](subsurface_water_and_heat.md#1-water-potentials) |
| (not covered) | `ECO_ET_col` is a year-to-date cumulative reset on day 1; canopy radiation uses a moisture-independent ground albedo; ground roughness is hard-coded; root water reaches the soil one hour after its transpiration | [surface page §1](surface_energy_balance_and_snow.md#1-eco_et_col-producing-equation-and-decomposition) |

## Coupling with other subsystems

- **Plant_bgc.** Supplies canopy transpiration, interception evaporation and root uptake (`UptakesMod.F90`), the canopy radiation model and roughness (`SurfaceRadiationMod.F90:82-183`, `CalcBoundaryLayerProperties`), and the ground SW `RadSWGrnd_col` (`SurfaceRadiationMod.F90:567`). Receives `HYCDMicP4RootUptake_vr` (`SoilHydroParaMod.F90:122-123`), consumed in `CalcPlantHydroResistance` (`UptakesMod.F90:1280`).
- **Transport.** Consumes `WaterFlow2MicPM_3D`, `WaterFlow2MacPM_3D`, the per-iteration pore volumes and the soil-air gas conductance `CondGasXSnowM_col` (`SurfPhysMod.F90:1155`, `InitSurfModelM`).
- **Microbial_bgc and Geochem.** Read water-filled and air-filled porosity, temperatures and potentials produced here.
- **Balances.** `redist` calls `SnowMassUpdate` (`Balances/RedistMod.F90:127`), `HandleSurfaceBoundary` (`:129`), `SnowpackLayering` (`:145`) and, through `AddFlux2SurfaceResidue`, `UpdateLitRPhys` (`:1364`).
- **Warming experiments.** `watsub` applies soil-cable warming when `check_warming_dates` is true (`WatsubMod.F90:118-122`; layer update at `:1410-1418`).

## Calibration parameters

This topic owns no plant or microbial file parameter of its own. File parameters that do reach ET from other surfaces (plant RSMX, RCS, OSMO, IGTYP, ISNTYP; grid ALBS, PSIFC, PSIWP) are mapped with their use sites in [surface_energy_balance_and_snow.md](surface_energy_balance_and_snow.md#calibration-parameters-source-map) and [subsurface_water_and_heat.md](subsurface_water_and_heat.md#calibration-parameters-source-map). Most hydrothermal coefficients (roughness, emissivities, litter albedo, surface resistances, retention exponent) are hard-coded constants with no file lever.
