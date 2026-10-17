---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/Transport/Nonsalt/` (gas phase and gas-water exchange), with the emission assembly in `f90src/Balances/RedistMod.F90`
**Last verified:** 2026-10-15
---

# Gas transport

Gas transport runs in the fast inner loop of `TranspNoSalt`: within each of the `NPH` water iterations, `NPT` gas sub-steps move soil-air gas by diffusion and water-displacement advection, exchange it with the atmosphere through the litter/snow boundary layer, and equilibrate it with the aqueous phase. See [index.md](index.md) for the driver and [solute_transport.md](solute_transport.md) for the aqueous phase.

## 1. Tracers and the fast loop

Gas tracers are fixed integer indices (`f90src/Modelconfig/TracerIDMod.F90:13-20`): `idg_CO2=1`, `idg_CH4=2`, `idg_O2=3`, `idg_N2=4`, `idg_N2O=5`, `idg_H2=6`, `idg_AR=7`, `idg_NH3=8`; the banded-fertiliser ammonia `idg_NH3B = idg_NH3+1` is assigned at run time and is the last gas index (`:183-184`, `InitTracerIDs`). Gas-phase loops run `idg_beg:idg_NH3`; NH3B exists only in the aqueous phase and exchanges with the NH3 gas pool through the banded pore volumes.

`TransptFastNoSaltMM` (`f90src/Transport/Nonsalt/TranspNoSaltFastMod.F90:35-92`) repeats, at most three times while the flux limiter is still shrinking (`:55`): zero fluxes (`:59`), litter volatilisation and dissolution (`LitterGasVolatilDissolMM`, `:61`), atmosphere-topsoil exchange (`SurfSoilFluxGasDifAdvMM`, `:63`), inter-grid transport and in-layer dissolution (`TracerFlowXGridsMM`, `:65`), lateral boundaries (`:67`), gathering, update and accumulation (`:69-73`); then applies BGC gas sources and sinks (`ApplyFastSourceSink`, `:87`) and checks mass (`:89`). Inside `TracerFlowXGridsMM` each layer first dissolves or volatilises (`GasDissolutionMM`, `:1010`) and each interface then transports (`GasTransportMM`, `:1049`).

## 2. Soil-air diffusion and advection

`GasTransportMM` (`TranspNoSaltFastMod.F90:513-542`) acts only when both cells have air-filled porosity above `AirFillPore_Min = 1E-3` (`f90src/Utils/EcoSimConst.F90:44`) and significant air volume (`:529-532`); it calls diffusion then advection.

**Diffusion** (`GasDiffusionMM`, `:779-812`):

```
DFLG2 = 2*POROQ*thetaA_src^2/POROS_src * AREA/DLYR_src           :795
DFLGL = 2*POROQ*thetaA_dst^2/POROS_dst * AREA/DLYR_dst           :797
CNDC1 = DFLG2*GasDifctScaledMM_vr(idg,src);  CNDC2 = DFLGL*GasDifctScaledMM_vr(idg,dst)     :801-802
GasDifuscoefMM_3D = CNDC1*CNDC2/(CNDC1 + CNDC2)                  :803
flux = GasDifuscoefMM_3D*(C_src - C_dst),  C = max(0, gas mass)/air volume     :807-809
```

`POROQ = 0.66` (`EcoSimConst.F90:38`), so the tortuosity factor is `thetaA^2*0.66/porosity`, a Millington-type reduction. `GasDifctScaledMM_vr` is the temperature-scaled free-air diffusivity times the gas time step.

**Advection by displaced air** (`UpstreamGasAdvectionMM`, `:588-633`): water entering the destination pushes its air back, and water leaving it draws air in:

```
FLQW = WaterFlow2SoilMM_3D(N,dst)                                               :604
FLQW > 0:  VFLW = -max(0, min(VFLWX, FLQW/VLsoiAirPM_dst));  flux = VFLW*max(0, gas_dst)   :609-618
FLQW <= 0: VFLW = -min(0, max(-VFLWX, FLQW/VLsoiAirPM_src)); flux = VFLW*max(0, gas_src)   :622-629
```

with `VFLWX = 0.5` (`TranspNoSaltDataMod.F90:11`) capping the fraction of a cell's gas moved per sub-step. `WaterFlow2SoilMM_3D` is the micropore plus macropore water flux of the current water iteration times `dt_GasCyc` (`TranspNoSaltMod.F90:408`, `:422`, `PassSlow2FastIterationM`).

## 3. Atmospheric boundary

**Soil surface** (`SurfSoilFluxGasDifAdvMM`, `TranspNoSaltFastMod.F90:443-475`), only when the top layer is air-filled soil (`:462-463`):

```
DFLG2   = thetaA*POROQ*thetaA/POROS * AREA/max(ZERO2, DLYR)             top layer           :830-832
GasDifuscoefMM_3D = DFLG2*GasDifctScaledMM_vr(idg,top)                                     :835
DGQ_cef = GasDifuscoefMM_3D*PARGas_CefMM/(GasDifuscoefMM_3D + PARGas_CefMM)                :846
flux    = DGQ_cef*(AtmGasCgperm3_col - C_top)                          Atm2TopSoilGasDifussionMM   :848
advection with the top-layer water flux: air leaves with infiltration, atmospheric air enters with drainage   Atm2TopSoilGasAdvectionMM, :490-508
```

`PARGas_CefMM(idg) = CondGasXSnowM_col(M)*dt_GasCyc*factor(idg)` (`TranspNoSaltMod.F90:395-403`), and `CondGasXSnowM_col = AREA*dts_HeatWatTP/(ResistBndlSurf_col + RAS)` comes from HydroTherm (`f90src/HydroTherm/SurfPhys/SurfPhysMod.F90:1155`, `InitSurfModelM`): the ground boundary-layer resistance, weighted between exposed soil and litter through the litter vapour-diffusion resistance, plus the snowpack resistance `RAS`. Thick or wet litter and deep snow therefore throttle soil-atmosphere gas exchange the same way they throttle bare-soil evaporation ([../hydrotherm/surface_energy_balance_and_snow.md](../hydrotherm/surface_energy_balance_and_snow.md#6-the-litter-vapour-resistance-chain)). The diagnostic `GasXSurfConduct_col` is `CondGasXSurf_col = 1/(ResistBndlSurf_col + RAS)` (`SurfPhysMod.F90:1156`).

**Litter.** `LitterGasVolatilDissolMM` (`TranspNoSaltFastMod.F90:404-442`) equilibrates litter-water gases with litter air (`:428-432`); in the slow loop the litter water exchanges with the atmosphere through `PARR_col` (`f90src/Transport/Nonsalt/TranspNoSaltSlowMod.F90:1266-1270`, `AtmosLitterExchangeM`), with `PARR_col = AREA*dts_HeatWatTP/(ResistAreodynOverLitr_col + RAS)` (`SurfPhysMod.F90:441`, `SurfaceResistances`).

**The column surface flux.** Each fast sub-step adds the litter exchange and the top-layer vertical exchange to `GasDiff2Surf_fast_flx_col` (`TranspNoSaltFastMod.F90:352-353`, `AccumFastFluxesMM`), summed per iteration into `GasDiff2Surf_flx_col` (`:207`, `ExitMassCheck`); the slow loop adds the aqueous atmosphere exchange (`TranspNoSaltSlowMod.F90:346`, `ExitMassCheck`).

**Bottom and lateral boundaries.** Gas dissolved in drainage leaves as `trcs_drainage_flx_col` (`TranspNoSaltFastMod.F90:210`; slow loop `TranspNoSaltSlowMod.F90:356`); lateral boundary fluxes are in `XBoundaryFluxMM` (`TranspNoSaltFastMod.F90:637`).

## 4. Gas-water exchange

`GasDissolutionMM` (`TranspNoSaltFastMod.F90:545-585`), when the layer has water and air above `AirFillPore_Min` (`:558-559`):

```
RGas_Disol = DiffusivitySolutEffM * (gas*Vw*S - aq*Va)/(Vw*S + Va),   Vw*S = trcg_VLWatMicP_vr     :562-565
```

for CO2, CH4, O2, N2, N2O, H2 and Ar (`idg_beg:idg_NH3-1`, `:561`); NH3 and NH3B use the non-banded and banded air and water volumes (`:568-580`). `trcg_VLWatMicP_vr` is the water volume times the Henry-law solubility `GasSolbility_vr`. The dribble correction in the numerator is multiplied by zero (`:564`), so it is inactive.

## 5. Ebullition

`BubbleEffluxM` (`TranspNoSaltSlowMod.F90:2727-2853`) runs once per water iteration when `ldo_transpt_bubbling = .true.` (default, `f90src/Modelconfig/EcoSIMCtrlMod.F90:83`; call at `TranspNoSaltMod.F90:336`):

```
DO N3 = NLF_col, NUM_col, -1                                            sweep upward              :2755
  if theta_w > air-dry and no dry layer met yet:                                                  :2759-2760
    dPond = max(0, layer bottom - water-table depth)*10                                           :2762
    VTATM = max(0, (PBOT_col + dPond)*Vw/(RGasC*TKS))*1E3     moles the water can hold            :2780
    VTGAS = sum over gases of aqueous mass/(MolecularWeight*GasSolbility)                          :2772, :2781
    if VTGAS > VTATM:  FracEbu = min(0, 0.5*(VTATM - VTGAS)/VTGAS)                                 :2786-2788
       each gas loses FracEbu*aqueous mass                                                        :2790-2792
       top layer or below the water table: to trcg_ebu_flx_col (emitted)                          :2798-2804
       otherwise: into that layer's gas phase                                                     :2805-2819
  else (a dry layer): accumulated ebullition is put back into the gas phase                       :2825-2845
```

**The sweep starts at `NLF_col`, which is not "the first unfrozen layer".** `NLF_col` is set by `watsub` to the shallowest layer whose ice fraction exceeds 0.9 (`f90src/HydroTherm/SoilPhys/WatsubMod.F90:184-187`), is initialised to 0 (`f90src/Ecosim_datatype/GridDataType.F90:40`) and is never reset. Consequences: in a column whose soil has never been more than 90% frozen, `NLF_col = 0 < NUM_col` and the `DO` loop executes zero times, so **ebullition never occurs**, whatever the CH4 or CO2 supersaturation; once a layer has frozen, ebullition sweeps from that layer upward for the rest of the run, even after thaw. Layers below `NLF_col` never bubble.

Ebullition from O2 and CH4 is also booked in `RO2AquaSourcePrev_vr` and `RCH4PhysexchPrev_vr` for the microbial model (`:2822-2823`).

## 6. Mass check and the surface emission

`ExitMassCheck` (`TranspNoSaltMod.F90:123-292`) forms, for each gas,

```
SurfGasEmiss_flx_col = trcg_ebu_flx_col + GasDiff2Surf_flx_col + Gas_WetDeposit_flx_col           :164-165
errmass = -(mass_now - mass_beg) + SurfGasEmiss_flx_col + GasHydroLoss_flx_col
          + RGasNetProd_col + dribble                                                             :186-189
RGasNetProd_col += trcs_Soil2plant_uptake_col   (reporting only, after errmass)                    :191
```

and aborts on `|errmass| > 1E-4` with `|errmass/delta| > 1E-3` (`:198`, `:286-287`), after writing the decomposition to unit 121.

## 7. CO2_SEMIS_FLX_col: producing chain

```
CO2_SEMIS_FLX_col = SurfGasEmiss_all_flx_col(idg_CO2)/AREA * GramPerHr2umolPerSec(idg_CO2)        f90src/IOutils/HistData/HistUpdateColumn.F90:242 (update_hist_columns)
SurfGasEmiss_all_flx_col = SurfGasEmiss_flx_col                                                  RedistMod.F90:172-174 (UpdateOutputVars)
                         + TRootGasLossDisturb_col + trcg_air2root_flx_col                      RedistMod.F90:210-214
trcg_air2root_flx_col    = sum over layers of trcg_air2root_flx_vr                               RedistMod.F90:984-986 (UpdateChemInSoilLays)
```

So the CO2 surface flux has three parts: the soil-surface flux from transport (ebullition, diffusion and advection at the soil and litter surface, wet deposition), the gas exchanged between roots and the atmosphere through plant tissue (`trcg_air2root_flx_col`, also written separately as `CO2_PLTROOT_FLX_col`, computed in the plant root gas model, see [../plant_bgc/roots_and_uptake.md](../plant_bgc/roots_and_uptake.md)), and disturbance root-gas losses (`TRootGasLossDisturb_col`). The block at `RedistMod.F90:184-208`, gated on `NU_col > NUI_col`, contains an unconditional `cycle` at `:190`, so its removal of gas from buried surface layers is dead code; the root-to-air and disturbance terms at `:210-214` are added regardless. CH4 and O2 use the same form (`HistUpdateColumn.F90:246-247`; CH4 is converted with the CO2 factor), while N2O, N2, NH3 and H2 are written per area without the umol conversion (`:293-296`). Production of the CO2 itself (heterotrophic and root respiration) is documented on the microbial and plant pages; on this page, the levers on how much reaches the surface in a given hour are hydrological (air-filled porosity, water flow, the litter and snow boundary resistance), all hard-coded or site properties.

## 8. Gas flux outputs

All are written in `update_hist_columns` (`f90src/IOutils/HistData/HistUpdateColumn.F90`) and registered in `HistRegisterColumn.F90`. The surface flux and its parts can be compared directly: the `SEMIS` total equals the soil-surface parts (diffusion and ebullition, plus wet deposition) plus the plant-root part (`PLTROOT`) plus disturbance losses.

| Output (registration line) | Source variable (update line) | Meaning |
|---|---|---|
| `CO2_SEMIS_FLX_col` (`:691`), `CH4_SEMIS_FLX_col` (`:705`), `O2_SEMIS_FLX_col` (`:808`) | `SurfGasEmiss_all_flx_col` (`:242`, `:246`, `:247`) | Total column-atmosphere flux, umol m-2 s-1 |
| `N2O_SEMIS_FLX_col` (`:876`) and the N2, NH3, H2 analogues | `SurfGasEmiss_all_flx_col` (`:293-296`) | Same, in g m-2 h-1 without the umol conversion |
| `CO2_DIF_FLX_col` (`:773`), `CH4_DIF_FLX_col` (`:783`) | `GasDiff2Surf_flx_col` (`:259-260`) | Diffusive and advective exchange at the soil and litter surface (§3) |
| `CH4_EBU_FLX_col` (`:710`) | `trcg_ebu_flx_col` (`:248`) | Ebullition (§5); zero in a never-frozen column |
| `CO2_PLTROOT_FLX_col` (`:753`), `CH4_PLTROOT_FLX_col` (`:744`) | `trcg_air2root_flx_col` (`:252-253`) | Root-atmosphere exchange through plant tissue (§7) |
| `GasXSurfConduct_col` (`:820`) | `CondGasXSurf_col` (`:272`) | Soil-air to atmosphere conductance [m/h] from the ground and snow boundary resistances |
| `CO2_DRAINLOSS_col`, `CO2_Cum_Hyd_Loss_col` | `trcs_drainage_flx_col`, `GasHydroLoss_cumflx_col` (`:266-267`) | Dissolved-CO2 loss with drainage and runoff |

Sign: the `*_FLX` gas outputs inherit the transport sign convention, positive into the soil, so emission to the atmosphere is negative; check the sign of `CO2_SEMIS_FLX_col` against an observed efflux before comparing.

## Calibration parameters

None. No plant, microbial or grid file parameter is read by the gas transport code; see [index.md](index.md#calibration-parameters).
