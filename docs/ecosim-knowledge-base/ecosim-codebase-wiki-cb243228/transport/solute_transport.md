---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/Transport/Nonsalt/` (aqueous phase) and `f90src/Transport/Salt/`
**Last verified:** 2026-10-15
---

# Solute transport

Aqueous transport moves dissolved gases, N and P nutrients and dissolved organic matter (and, with `salt_model`, salt ions and complexes) at the water-iteration cadence `M = 1..NPH`, using the water fluxes `watsub` stored for that iteration. The non-salt solver is `TransptSlowNoSaltM` (`f90src/Transport/Nonsalt/TranspNoSaltSlowMod.F90:42-102`); the salt solver is `TranspSalt` (`f90src/Transport/Salt/TranspSaltMod.F90:41-91`). See [index.md](index.md) for the driver and [gas_transport.md](gas_transport.md) for the gas phase.

## 1. Tracers

Indices are set at run time in `InitTracerIDs` (`f90src/Modelconfig/TracerIDMod.F90:170-402`), so names, not numbers, are load-bearing.

| Range | Members | Defined at |
|---|---|---|
| dissolved gases `idg_beg:idg_NH3` | CO2, CH4, O2, N2, N2O, H2, Ar, NH3 (fixed 1-8) | `TracerIDMod.F90:13-21` |
| banded nutrients `ids_nutb_beg:ids_nutb_end` | NH3B, NH4B, NO3B, NO2B, H1PO4B, H2PO4B | `:183`, `:188-195` |
| non-banded nutrients `ids_nut_beg:ids_nuts_end` | NH4, NO3, NO2, H1PO4, H2PO4 | `:197-204` |
| all solutes `ids_beg:ids_end` | the above, starting at `idg_CO2` | `:178`, `:187` |
| DOM `idom_beg:idom_end` | DOC, DON, DOP, acetate, each per litter/SOM complex `K` | `:229-233` |

`ids_nuts_beg = idg_NH3` (`:186`), so the "nutrient" range starts at aqueous NH3 and includes NH3B and all banded and non-banded N and P species. Banded tracers live in the fertiliser band volume: each layer is split by `trcs_VLN_vr(ids,...)` into band and non-band fractions, and every kernel weights by them. Solubility caps: `tracerSolc_max` for NH3, NH4, NO3 (`:206-214`).

## 2. The slow loop

```
TransptSlowNoSaltM                                       TranspNoSaltSlowMod.F90:42
  EnterMassCheck                                         :56
  StageSlowTranspIterationM                              :61
  DO WHILE (dpscal_max > 1E-2 .and. iterm < 3)           :63
    ZeroFluxesM                                          :67
    SnowSoluteVertDrainM        snow drainage            :69
    SurfaceSoluteFluxM          atmosphere, litter, runoff   :71
    TracerXBoundariesM          lateral and bottom boundaries   :73
    TracerXInterGridsM          interior transport       :75
    GatherTranspFluxM                                    :77
    SlowUpdateStateVarsM        apply fluxes with limiter pscal   :79
    AccumSlowFluxesM                                     :81
    dpscal = dpscal*(1 - pscal) per tracer and DOM; dpscal_max = max      :83-96
  ApplySlowSourceSink           BGC sources and sinks, once            :98
  ExitMassCheck                                          :100
```

Each pass re-runs transport with the remaining fraction of the flux after the previous pass's non-negativity limiter; the loop stops after three passes or when every tracer's remaining fraction is below 1%.

`TracerXInterGridsM` (`:1087-1143`) first exchanges solute between macropores and micropores within each layer (`MicMacPoresSoluteExchM`, `:1106`; advective `:2581-2668`, diffusive `:2669-2726`) and then, for each interface, calls `SoluteAdvDifusTranspM` (`:1131`; `:1933-1960`), which runs micropore advection (`:1948`), micropore diffusion-dispersion (`:1950`), macropore advection (`:1954`) and macropore dispersion (`:1956`) in that order.

## 3. Advection

`MicroporeSoluteAdvectionM` (`TranspNoSaltSlowMod.F90:2489-2552`) is first-order upwind:

```
Q > 0:  VFLW = max(0, min(VFLWX, Q/VLWatMicPM_src));  flux = VFLW*max(0, C_src)     :2501-2514
Q <= 0: VFLW = min(0, max(-VFLWX, Q/VLWatMicPM_dst)); flux = VFLW*max(0, C_dst)     :2517-2529
```

with `Q = WaterFlow2MicPM_3D(M,N,dst)` and `VFLWX = 0.5` (`TranspNoSaltDataMod.F90:11`): at most half of a cell's solute moves per iteration, and negative concentrations are clipped. DOM is advected the same way per complex (`:2509`, `:2525`). Macropore advection uses the macropore water flux and volumes (`MacroporeSoluteAdvectionM`, `:2171-2281`; `VFLW` at `:2191`, `:2241`).

## 4. Diffusion and dispersion

`MicroporeSoluteDiffusionM` (`TranspNoSaltSlowMod.F90:1962-2170`):

```
TORTL = (TortMicPM_src*DLYR1 + TortMicPM_dst*DLYR2)/(DLYR1 + DLYR2)                               :2119
DISPN = DISP_3D(N,dst)*min(VFLWX, |WaterFlow2MicPM_3D|/AREA)                                       :2120
SDifc = (SoluteDifusivitytscaledM_vr(ids,dst)*TORTL + DISPN)*XDPTH_3D(N,dst)                       :2127
flux  = SDifc*(C_src - C_dst)            gases                                                     :2137
flux  = SDifc*(C_src - C_dst)*min(trcs_VLN_src, trcs_VLN_dst)   band/non-band nutrients           :2141
```

with the DOM analogue at `:2123`. The geometry is set once at start-up (`f90src/Ecosim_mods/StartsMod.F90:304-314`, `InitSoilVars`): `DIST_3D = 0.5*(DLYR_src + DLYR_dst)`, `XDPTH_3D = AREA/DIST_3D`, and the longitudinal dispersivity `DISP_3D = 0.20*DIST_3D**1.07` (the source comment asks for a reference). Dispersion grows linearly with the interstitial velocity up to the `VFLWX` cap. `MacroporeSoluteDispersionM` (`:2282-2488`) is the macropore counterpart.

## 5. Surface, litter and snow

`SurfaceSoluteFluxM` (`TranspNoSaltSlowMod.F90:1187-1234`) handles exchange of litter water with the atmosphere (`AtmosLitterExchangeM`, `:1235-1280`, using the litter-air conductance `PARR_col`, `:1266-1270`), of the top-soil water with the atmosphere (`AtmosSoilExchangeM`, `:1281-1384`), litter-soil advection (`Lit2SoilTracerAdvectM`, `:1385-1458`) and litter-soil diffusion with dispersion (`LitterSoilTracerDiffusionM`, `:1459-1549`; `DISPN` at `:1511`). Surface runoff carries litter-water solutes (`TracerFlowThruSurRofM`, `:1619-1743`); snow redistribution and snowmelt carry snowpack solutes (`TracerFlowThruSnowRedist`, `:1744-1821`; `SnowSoluteVertDrainM`, `:1822-1932`).

**Wet deposition** (`SoluteWetDeposition`, `f90src/Transport/Nonsalt/InitNoSaltTransportMod.F90:89-128`) routes rain and irrigation solutes to the snowpack when snow falls or rain hits a significant snowpack (`TracerFall2Snowpack`, `:518-546`) and to litter and soil otherwise (`TracerFall2Grnd`, `:547`). The diagnostic `NWetDep_col` (inorganic N wet deposition, output `Ni_cumWetDep_col`, `f90src/IOutils/HistData/HistRegisterColumn.F90:907`) is incremented only in `TracerFall2Snowpack` (`:529`), so N deposited directly on snow-free ground is not counted in it; the accumulator is reset yearly (`f90src/Modelforc/YearMod.F90:55`).

## 6. Boundaries

`TracerXBoundariesM` (`TranspNoSaltSlowMod.F90:3167-3265`) exports solutes through lateral faces and the bottom: subsurface flow through the grid boundary (`XBoundaryTracerTranspXYZM`, `:3009-3104`) and surface runoff off the landscape edge (`XSurfBoundaryTracerRunoffXYM`, `:3105-3166`), conditional on `FlowDirIndicator_col` and the boundary run-on/run-off factors. Bottom drainage leaves as `trcs_drainage_flx_col`; lateral subsurface loss is `trcs_SubsurTransp_flx_2DH`.

## 7. Source and sink coupling

Biological and chemical rates are converted to per-iteration amounts during staging (`StageSurfaceFluxes`, `InitNoSaltTransportMod.F90:132-242`; `StageSoilFluxes`, `:374-517`) and applied after the limiter loop by `ApplySlowSourceSink` (`TranspNoSaltSlowMod.F90:104-163`): for litter NH3, nutrients and DOM (`:113-136`) and for every solute in each soil layer (`:138-149`), `state += source`, then the sink is removed through `SubstrateDribbling`, which defers any part that would drive the pool negative into a "dribble" store repaid later (`:115`, `:123`, `:132`, `:142`). Net production accumulates into `trcs_NetProd_slow_flxM_col` for the mass check (`:118`, `:126`, `:145`).

| Process | Enters as | Produced in |
|---|---|---|
| Microbial mineralisation, nitrification, denitrification, DOM uptake | `RBGCSrcSoluteM_vr`, `RBGCSinkSoluteM_vr`, `RBGCSink_DOM_micpM_vr` | `Microbial_bgc` |
| Root uptake of NH4, NO3, H2PO4, H1PO4 and gases | sinks; column totals `trcs_Soil2plant_uptake_col` | `Plant_bgc` |
| Aqueous NH3 chemistry in litter | `TRProd_chem_sol_NH3_soil_vr` (`InitNoSaltTransportMod.F90:213-218`) | `Geochem` (`soluteModel`, before transport) |
| Litter microbial gas uptake | `RBGCSinkGasMM_vr`, `RBGCSrceGasMM_vr` with the non-negative dribble repayment (`:203-211`) | `Microbial_bgc` |

## 8. Mass check and diagnostics

`ExitMassCheck` (`TranspNoSaltSlowMod.F90:263-468`) compares the change in gas, solute and DOM inventories over the snow, litter and soil with the boundary losses and net production for each iteration, and accumulates the hourly column fluxes (`:345-357`): `GasDiff2Surf_flx_col`, `GasHydroLoss_flx_col`, `Gas_WetDeposit_flx_col`, `RGasNetProd_col`, `trcs_drainage_flx_col`.

**Nutrient hydrological-loss diagnostic indexes the wrong tracer.** New at cb243228:

```
do ids = ids_nuts_beg, ids_nuts_end
  trcnuts_hydrloss_flx_col(ids) += trcs_hydrloss_slow_flx_col(idg)        TranspNoSaltSlowMod.F90:342-344
enddo
```

`idg` is not the loop variable: it is left over from the preceding `DO idg=idg_beg,idg_NH3` loop (`:323-325`), whose exit value is `idg_NH3+1 = idg_NH3B`. Every nutrient therefore receives the banded-NH3 aqueous loss. `EndCheckBalances` sums NH4+NH4B and NO3+NO3B of this array into `Hydroloss_NH4_cumflx_col` and `Hydroloss_NO3_cumflx_col` (`f90src/ModelDiags/BalancesMod.F90:290-291`), which feed the outputs `NH3_Cum_Hyd_Loss_col` and `NO3_Cum_Hyd_Loss_col` (`f90src/IOutils/HistData/HistUpdateColumn.F90:268-269`). Both outputs report twice the NH3B loss, not ammonium or nitrate leaching. The transported masses and the mass check are unaffected; only these diagnostics are wrong. Use `trcs_drainage_flx_col` and the solute concentrations instead when nitrate leaching is needed.

## 9. Salt transport

`TranspSalt` (`TranspSaltMod.F90:41-91`) runs only with `salt_model` and has the same structure: per iteration, zero fluxes, compute all fluxes (`GetSaltTranspFlxM`, `f90src/Transport/Salt/IngridTranspMod.F90:28`), update with a limiter, accumulate, and repeat while `dpscal_max > 1E-2` (`TranspSaltMod.F90:70-87`). Unlike the non-salt loop there is no pass cap. Advection mirrors the non-salt kernel (`SoluteAdvMicroporeM`, `IngridTranspMod.F90:1051-1106`), with phosphate salts weighted by the non-band and band fractions `trcs_VLN_vr(ids_H1PO4)` and `trcs_VLN_vr(ids_H1PO4B)` (`:1075-1081`, `:1093-1098`). Diffusion, macropore transport, mic-mac exchange, snow, litter, runoff and boundary kernels are listed in [index.md](index.md#salt).

## 10. Outputs

| Output | Source variable |
|---|---|
| `NH3_Cum_Hyd_Loss_col`, `NO3_Cum_Hyd_Loss_col` | cumulative hydrological N loss (see the defect in §8) (`HistRegisterColumn.F90:731`, `:735`) |
| `CO2_DRAINLOSS_col`, `CO2_Cum_Hyd_Loss_col` | `trcs_drainage_flx_col`, `GasHydroLoss_cumflx_col` (`HistUpdateColumn.F90:266-267`; registered `HistRegisterColumn.F90:723`, `:727`) |
| `DOC_soil_col`, `DON_soil_col`, `DOP_soil_col`, `Acetate_soil_col` | DOM inventories |
| `cNO3_LITR_col`, `cNH4_LITR_col`, `cPO4_LITR_col` | litter-water concentrations |

## Calibration parameters

None. The aqueous transport code reads no plant, microbial or grid file parameter; see [index.md](index.md#calibration-parameters).
