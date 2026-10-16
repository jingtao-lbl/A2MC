---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/ModelDiags/` (5 files) and `f90src/DebugTools/` (1 file)
**Last verified:** 2026-10-15
---

# Model diagnostics (`f90src/ModelDiags/`)

`ModelDiags/` holds the hourly closure audit, three per-hour diagnostic calculations, and a set of organic-matter summation routines shared by the microbial, balance and history code. Two of the five files are new since `2dea74d9`.

## 1. Files

| file | lines | public routines | called from |
|---|---|---|---|
| `BalancesMod.F90` | 521 | `BegCheckBalances` (`:37`), `EndCheckBalances` (`:170`), `SummarizeTracerMass` (`:510`), `SummarizeSnowMass` (`:97`), `SummarizeTracers` (`:433`) (`:30-34`) | `hour1` (`f90src/Modelforc/Hour1Mod.F90:149`, `:151`); `Run_EcoSIM_one_step` (`drivers/ecosim/EcoSIMAPI.F90:124`); restart path (`:504`) |
| `HydrologyDiagMod.F90` | 123 | `DiagWaterTBLDepz` (`:23`) | `hour1` (`Hour1Mod.F90:178`) |
| `SoilDiagsMod.F90` | 70 | `DiagSoilGasPressure` (`:31`) | `Run_EcoSIM_one_step` (`EcoSIMAPI.F90:122`) |
| `MLDataDiagMod.F90` (new) | 270 | `MLDataDiag` (`:39`); helpers `compute_fcon_average` (`:135`), `compute_fmas_average` (`:198`), `check_interp` (`:258`) | `Run_EcoSIM_one_step` when `lmicrobeMLdiag` (`EcoSIMAPI.F90:66`) |
| `MicrobialDiagMod.F90` (new; routines moved from `SoilBGCNLayMod.F90`) | 531 | `sumORGMLayL` (`:44`), `SumSolidOML` (`:155`), `sumLitrOMLayL` (`:179`), `sumHumOMLayL` (`:262`), `sumMicBiomLayL` (`:336`), `sumSurfOMCK` (`:390`), `SumMicbGroup` (`:442`), `sumDOML` (`:508`) | `MicrobeModel` (`f90src/APIs/MicBGCAPI.F90:124-140`), `RedistMod` (`f90src/Balances/RedistMod.F90:688`, `:1264`, `:1271`), `hour1` (`Hour1Mod.F90:954`), history (`f90src/IOutils/HistData/HistUpdateColumn.F90:304-335`), `MLDataDiag` |

## 2. `BalancesMod`: the hourly closure audit

### 2.1 Bracket

`BegCheckBalances` copies the end-of-last-hour storages into "begin" slots (`:37-75`): column water and heat (`WaterErr_col = WatMass_col`, `HeatErr_col = HeatStore_col`), snow energy, canopy, snow, litter and soil water, the solute dribble buffers summed over layer 0 and `NU..NL` (`:55-63`), and gas totals for the column, soil, root and snow (`:65-72`). `EndCheckBalances` recomputes storages through `SummarizeTracerMass` (`:196`) and tests the residuals. Its water and tracer tests, the 1e-4 and 0.1 abort thresholds, and the unreachable energy test (the `cycle` at `:407`) are documented with all other checks in [../balances_and_disturbances/mass_balance.md](../balances_and_disturbances/mass_balance.md) §3. In short: soil water aborts at 1e-4, a gas tracer at 0.1 g, energy never.

### 2.2 Summarisers

- `SummarizeStorage` (`:77`) loops columns and calls `SumUpWaterStorage` (`:109`) and `SumUpHeatStorage` (`:144`). Canopy water now includes snow held on the canopy (`SnowOnCanopy_col`, added since `2dea74d9`).
- `SummarizeSnowMass` (`:97`) sums dry snow, liquid and ice over the snow layers.
- `SummarizeTracers` (`:433`) sums each gas over snow, roots and soil into `trcg_snowMass_col`, `trcg_rootMass_col`, `trcg_soilMass_col` and `trcg_TotalMass_col`.
- `SummarizeTracerMass` (`:510`) chains the storage and tracer summaries.

The audit also accumulates `Hydroloss_NH4_cumflx_col` and `Hydroloss_NO3_cumflx_col` (`:290-291`), `GasHydroLoss_cumflx_col` (`:299`) and `trcg_mass_cumerr_col` (`:318`). Two expressions there contain a doubled plus (`++trcnuts_hydrloss_flx_col(...)`, `:290-291`), which Fortran reads as a unary plus, so the sums are correct.

## 3. `DiagWaterTBLDepz` (`HydrologyDiagMod.F90:23`)

Diagnoses the internal water-table depth `DepzIntWTBL_col` from layer air-filled porosity, treating a layer as saturated when its air-filled porosity is below `THETPW = 0.01` (`HydrologyDiagMod.F90:43`, with `THETWP = 1 - THETPW` beside it). Called per column inside `hour1`.

## 4. `DiagSoilGasPressure` (`SoilDiagsMod.F90:31-69`)

For each soil layer with water and dissolved CO2 it converts dissolved gas mass into partial pressure, `GasPres = trcs_solml * RGasC * TKS / (MolecularWeight * GasSolbility * VLWatMicP)`, sums them into `Soil_Gas_pressure_vr`, and stores mole fractions in ppm in `Soil_Gas_Frac_vr`, folding the banded NH3 pseudo-gas into NH3. Layers without water get zero. These feed the `*_gas_ppmv_vr` history fields.

## 5. `MLDataDiag` (`MLDataDiagMod.F90:39`)

Writes features for machine-learning work: per column it walks down to the first layer whose bottom is at or below 0.6 m (`LF`), then averages over the top 0.3 m soil temperature, volumetric water, dissolved O2, CO2, H2, CH4 (concentration averages, `compute_fcon_average`), and DOC, acetate, CH4 production by pathway, aerobic CH4 oxidation, heterotrophic CO2, fermentation and several microbial group biomasses (mass averages, `compute_fmas_average`). `check_interp` aborts the run if an average cannot be evaluated (`:258-268`). Switching on `lmicrobeMLdiag` therefore adds an abort path, and a profile that never reaches 0.6 m leaves `LF` unset.

## 6. `MicrobialDiagMod`

Shared summation routines, now in their own module. `sumORGMLayL` sums all organic matter of a layer (litter, POM, humus, optionally carbon only); `sumMicBiomLayL` sums living microbial biomass; `SumMicbGroup` sums one functional group (heterotrophic or, with `isauto`, autotrophic), used for cyanobacterial PAR shading in `MicrobeModel` (`MicBGCAPI.F90:135`, `:140`) and for group outputs. In `MicrobeModel`, `sumMicBiomLayL` is called before and after each layer's `MicBGC1Layer` (`MicBGCAPI.F90:124-128`), but the difference is accumulated into a local `tdOrGM` that is neither initialised nor used: there is no microbial mass check.

## 7. `DebugToolMod` (`f90src/DebugTools/DebugToolMod.F90`)

`PrintInfo`, the generic `DebugPrint`, `do_debug` and `GetSoilWaterMass`; all printing is gated by `lverb` (`:32-37`, `:41-89`). See [../core/utilities.md](../core/utilities.md) §10.

## 8. Order inside the hour

```
PrepHourlyWeather                               EcoSIMAPI.F90:518   (before the step)
Run_EcoSIM_one_step                             EcoSIMAPI.F90:522
  HOUR1                                         :49
    [SummarizeTracerMass if soil reset]         Hour1Mod.F90:149
    BegCheckBalances                            Hour1Mod.F90:151
    per column ... DiagWaterTBLDepz             Hour1Mod.F90:178
  WATSUB (ExitMassBalanceM each sub-cycle)      :56
  MicrobeModel (sumMicBiomLayL per layer)       :63
  MLDataDiag if lmicrobeMLdiag                  :66
  PlantModel (Enter/ExitPlantBalance)           :73
  soluteModel, TranspNoSalt (ExitMassCheck), TranspSalt, EROSION, REDIST
  DiagSoilGasPressure                           :122
  EndCheckBalances                              :124
history update                                  EcoSIMAPI.F90:526
```

## 9. Side-channel files

| unit | written by | content |
|---|---|---|
| 110 | `EndCheckBalances` | column water budget dump (`BalancesMod.F90:232-270`) and the unreachable energy dump |
| 111 | `EndCheckBalances` | per-gas budget dump (`:324-396`) |
| 121 | `TranspNoSaltMod::ExitMassCheck` | transport gas budget dump (`f90src/Transport/Nonsalt/TranspNoSaltMod.F90:200` onward) |
| 888 | `CheckPlantBalanceZ` | plant C, N, P budget dump (`f90src/Plant_bgc/PlantBalMod.F90:854-936`) |
| 993-996 | `ExitMassBalanceM` | WATSUB water dumps (`f90src/HydroTherm/SoilPhys/WatsubMod.F90:253-284`) |
| 104 | `InitTracerIDs` | tracer id listing (`f90src/Modelconfig/TracerIDMod.F90:378-386`) |

None of these units is opened explicitly (the only `open` of one of them is commented out, `drivers/ecosim/ecosim.F90:57`), so each appears as `fort.<unit>` in the run directory on first write.

## Calibration parameters

None. Diagnostics hold no calibration parameter.
