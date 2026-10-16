---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/Transport/` (Nonsalt and Salt)
**Last verified:** 2026-10-15
---

# Transport subsystem

`f90src/Transport/` moves gases, non-salt solutes (dissolved gases, N and P nutrients, DOM) and, optionally, salt ions through the snow, litter and soil column and across lateral boundaries. It never computes water fluxes: it consumes the per-iteration water flows and pore volumes that `watsub` produced earlier in the hour ([../hydrotherm/index.md](../hydrotherm/index.md)), applies source and sink terms from the microbial, plant and geochemistry models, and reports surface emissions, drainage and runoff losses to `Balances`.

Between `2dea74d9` and `cb243228` this tree changed by 18 lines: a nutrient hydrological-loss diagnostic and a wet-N-deposition diagnostic were added, and the litter dribble sink was made non-negative. The equations are otherwise unchanged; the corrections on these pages concern semantics the previous wiki got wrong at both pins (ebullition, the composition of `CO2_SEMIS_FLX_col`).

## Call position

`Run_EcoSIM_one_step` calls `TranspNoSalt` every hour after `watsub`, the microbial and plant models and, if enabled, `soluteModel` (`drivers/ecosim/EcoSIMAPI.F90:91`), then `TranspSalt` when `salt_model` is true (`:98-102`; default `.false.`, `f90src/Modelconfig/EcoSIMCtrlMod.F90:65`). `redist` then assembles the column emission totals (`f90src/Balances/RedistMod.F90:160-274`, `UpdateOutputVars`).

## Files

### Nonsalt

| File (lines) | Main routines (header line) | Purpose |
|---|---|---|
| `TranspNoSaltMod.F90` (440) | `EnterMassCheck` (`:65`), `ExitMassCheck` (`:123`), `TranspNoSalt` (`:296`), `SummaryFluxes` (`:351`), `PassSlow2FastIterationM` (`:377`) | Hourly driver, per-tracer surface conductances, column mass check. |
| `TranspNoSaltSlowMod.F90` (3622) | `TransptSlowNoSaltM` (`:42`), `ApplySlowSourceSink` (`:104`), `ExitMassCheck` (`:263`), `TracerXInterGridsM` (`:1087`), `SurfaceSoluteFluxM` (`:1187`), `MicroporeSoluteDiffusionM` (`:1962`), `MicroporeSoluteAdvectionM` (`:2489`), `BubbleEffluxM` (`:2727`), `TracerXBoundariesM` (`:3167`) | Aqueous transport at the water-iteration cadence, ebullition. |
| `TranspNoSaltFastMod.F90` (1058) | `TransptFastNoSaltMM` (`:35`), `LitterGasVolatilDissolMM` (`:404`), `SurfSoilFluxGasDifAdvMM` (`:443`), `GasTransportMM` (`:513`), `GasDissolutionMM` (`:545`), `UpstreamGasAdvectionMM` (`:588`), `GasDiffusionMM` (`:779`), `Atm2TopSoilGasDifussionMM` (`:814`) | Gas-phase transport and gas-water exchange at the gas cadence. |
| `InitNoSaltTransportMod.F90` (615) | `InitTranspNoSaltModel` (`:43`), `SoluteWetDeposition` (`:89`), `StageSurfaceFluxes` (`:132`), `CopyTracerStates` (`:243`), `BackCopyStateVars` (`:318`), `StageSoilFluxes` (`:374`), `TracerFall2Snowpack` (`:518`), `TracerFall2Grnd` (`:547`) | Staging, wet deposition, BGC source/sink conversion to per-step rates. |
| `TranspNoSaltDataMod.F90` (468) | `InitTransfrData` (`:158`) | Work arrays; `XFRS = 0.05`, `VFLWX = 0.5` (`:10-11`). |

### Salt

| File (lines) | Main routines (header line) | Purpose |
|---|---|---|
| `TranspSaltMod.F90` (419) | `TranspSalt` (`:41`), `AccumSaltFluxesM` (`:94`), `UpdateSaltTranspM` (`:322`) | Salt driver: `NPH` iterations, each with an uncapped limiter loop (`:65-88`). |
| `IngridTranspMod.F90` (1625) | `GetSaltTranspFlxM` (`:28`), `SurfaceSaltFluxM` (`:50`), `SaltXGridBoundTransptM` (`:136`), `SnowSaltTranptM` (`:524`), `SoluteAdvMicroporeM` (`:1051`), `SoluteDifsMicroporeM` (`:1108`), `SoluteAdvMacroporeM` (`:1237`), `SoluteDifsMacroporeM` (`:1328`), `SaltTranspXInterGridsM` (`:1530`) | Salt kernels mirroring the non-salt ones. |
| `TranspSaltDataMod.F90` (98) | `InitTranspSaltData` (`:41`) | Salt work arrays; `VFLWX = 0.5` (`:12`). |

## Structure of one hour

```
TranspNoSalt                                   TranspNoSaltMod.F90:296
  EnterMassCheck                               :312
  InitTranspNoSaltModel (staging, wet deposition, BGC rates)   :314
  DO M = 1, NPH                                :322
    TransptSlowNoSaltM   aqueous transport, limiter loop (<= 3 passes)   :326
    PassSlow2FastIterationM  gas conductances, carrier water fluxes      :329
    DO MM = 1, NPT: TransptFastNoSaltMM   gas transport, dissolution    :331-333
    BubbleEffluxM   if ldo_transpt_bubbling                              :336
  BackCopyStateVars, SummaryFluxes, ExitMassCheck                        :340-344
```

`dt_GasCyc = 0.99999/NPT` and `dts_gas = 0.99999/(NPH*NPT)` (`f90src/Ecosim_mods/StartsMod.F90:970-971`, `set_ecosim_solver`). Every kernel is written for a source cell `(N3,N2,N1)` and a destination `(N6,N5,N4)` in direction `N` (1 west-east, 2 north-south, 3 vertical), starting at `FlowDirIndicator_col` so that column runs skip the lateral directions.

## Coupling with HydroTherm

| Transport input | Produced in HydroTherm |
|---|---|
| `WaterFlow2MicPM_3D(M,...)`, `WaterFlow2MacPM_3D(M,...)` | `Subsurface3DInternalFlowM`, `f90src/HydroTherm/SoilPhys/WatsubMod.F90:778-779`; top boundary `f90src/HydroTherm/SurfPhys/SurfPhysMod.F90:1097-1098` |
| `VLWatMicPM_vr`, `VLWatMacPM_vr`, `VLsoiAirPM_vr`, `FracAirFilledSoilPoreM_vr` | `LocalCopySoilVars` and the per-iteration updates in `WatsubMod.F90` |
| `CondGasXSnowM_col(M)` (soil-air-to-atmosphere conductance) | `InitSurfModelM`, `SurfPhysMod.F90:1155`, from the litter-weighted ground boundary-layer resistance and the snowpack resistance |
| `PARR_col` (litter-air conductance) | `SurfaceResistances`, `SurfPhysMod.F90:441` |
| `NLF_col` (start of the ebullition sweep) | `watsub`, `WatsubMod.F90:184-187` |

Per-tracer surface conductances scale `CondGasXSnowM_col*dt_GasCyc` by molecular-diffusivity factors CO2 0.74, CH4 1.04, O2 0.83, N2 0.86, N2O 0.74, NH3 1.02, H2 2.08, Ar 0.72 (`TranspNoSaltMod.F90:395-403`).

## Limiters and mass checks

The non-salt aqueous loop repeats zero-fluxes, snow drainage, surface fluxes, boundaries, inter-grid transport, gathering, update and accumulation while `dpscal_max > 1E-2` and at most 3 passes (`TranspNoSaltSlowMod.F90:63-97`), shrinking each tracer's flux by its `pscal` limiter. Source and sink rates are applied once after the loop (`ApplySlowSourceSink`, `:98`). The salt loop has the same form without a pass cap (`f90src/Transport/Salt/TranspSaltMod.F90:70-87`). The hourly gas check aborts when `|err| > 1E-4` and `|err/delta| > 1E-3` (`TranspNoSaltMod.F90:198`, `:286-287`).

## What the previous wiki got wrong

Each item is verified at cb243228 and detailed on the linked page; the full audit is `memory/dev_logs_adapterkit/ecosim_wiki_audit_cb243228/06_hydrotherm_transport.md` (dev repo only).

| Previous claim | Fact at cb243228 | Where |
|---|---|---|
| Ebullition sweeps up from "the first unfrozen layer" `NLF_col` | `NLF_col` is the shallowest layer ever more than 90% ice, 0 if none; in a never-frozen column the sweep never runs and ebullition is off | [gas_transport.md](gas_transport.md#5-ebullition) |
| `CO2_SEMIS_FLX_col` reduces to the soil-surface flux | It also contains the root-atmosphere plant flux `trcg_air2root_flx_col` and disturbance losses (`f90src/Balances/RedistMod.F90:210-214`) | [gas_transport.md](gas_transport.md#7-co2_semis_flx_col-producing-chain) |
| Mic-mac exchange runs after advection and diffusion | It runs first in each layer (`TranspNoSaltSlowMod.F90:1106`), then `SoluteAdvDifusTranspM` (`:1131`) | [solute_transport.md](solute_transport.md#2-the-slow-loop) |
| The salt loop iterates "until convergence" | Same limiter test, no pass cap (`f90src/Transport/Salt/TranspSaltMod.F90:70`) | [solute_transport.md](solute_transport.md#9-salt-transport) |
| (not covered) | New diagnostic `trcnuts_hydrloss_flx_col` indexes the wrong tracer, so `NH3_Cum_Hyd_Loss_col` and `NO3_Cum_Hyd_Loss_col` report banded-NH3 loss (`TranspNoSaltSlowMod.F90:342-344`) | [solute_transport.md](solute_transport.md#8-mass-check-and-diagnostics) |
| (not covered) | `NWetDep_col` counts only N deposited onto snow (`InitNoSaltTransportMod.F90:529`) | [solute_transport.md](solute_transport.md#5-surface-litter-and-snow) |

## Outputs at a glance

| Tracer group | Main outputs | Page |
|---|---|---|
| Gas surface fluxes | `CO2_SEMIS_FLX_col`, `CH4_SEMIS_FLX_col`, `O2_SEMIS_FLX_col`, `N2O_SEMIS_FLX_col`; parts `*_DIF_FLX_col`, `*_EBU_FLX_col`, `*_PLTROOT_FLX_col` | [gas_transport.md](gas_transport.md#8-gas-flux-outputs) |
| Gas hydrological loss | `CO2_DRAINLOSS_col`, `CO2_Cum_Hyd_Loss_col` | [gas_transport.md](gas_transport.md#8-gas-flux-outputs) |
| Nutrient hydrological loss | `NH3_Cum_Hyd_Loss_col`, `NO3_Cum_Hyd_Loss_col` (defective, see above) | [solute_transport.md](solute_transport.md#8-mass-check-and-diagnostics) |
| DOM and litter-water solutes | `DOC_soil_col`, `DON_soil_col`, `DOP_soil_col`, `Acetate_soil_col`, `cNO3_LITR_col`, `cNH4_LITR_col`, `cPO4_LITR_col` | [solute_transport.md](solute_transport.md#10-outputs) |
| Boundary conductance | `GasXSurfConduct_col` | [../hydrotherm/surface_energy_balance_and_snow.md](../hydrotherm/surface_energy_balance_and_snow.md#6-the-litter-vapour-resistance-chain) |

## Pages

- [gas_transport.md](gas_transport.md): gas diffusion and advection, the atmospheric boundary, gas-water exchange, ebullition, the `CO2_SEMIS_FLX_col` producing chain.
- [solute_transport.md](solute_transport.md): aqueous advection-dispersion, tracers, macropore-micropore exchange, source-sink coupling, boundaries, diagnostics.

## Calibration parameters

None. Every coefficient in this subsystem is a hard-coded constant (`VFLWX`, `XFRS`, `POROQ`, the diffusivity ratios, the dispersivity rule) or a site physical property; transport carries no plant, microbial or grid file parameter. Calibration leverage on the gas and solute outputs sits in the processes that produce or consume the tracers, and in the hydrology that moves the water.
