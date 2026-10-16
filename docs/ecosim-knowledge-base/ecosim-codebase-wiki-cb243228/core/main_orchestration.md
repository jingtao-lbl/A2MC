---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `drivers/ecosim/{ecosim,EcoSIMAPI}.F90`, `f90src/Main/`, `f90src/Ecosim_mods/`, and the call targets that make up one simulated hour
**Last verified:** 2026-10-15
---

# Main orchestration: startup, the year, the day, the hour, shutdown

This page follows one standalone EcoSIM run from `program main` down to the hourly calls into the plant, microbial, hydrothermal and balance code. The library modules in `f90src/Main/` and `f90src/Ecosim_mods/` allocate and initialise state; the time loop itself lives in the driver (`drivers/ecosim/`). The ATS-coupled path is a different driver and is covered in the APIs section.

## 1. The driver program (`drivers/ecosim/ecosim.F90`)

`program main` (`drivers/ecosim/ecosim.F90:1`) runs this fixed sequence:

| step | call | line | what it does |
|---|---|---|---|
| 1 | `namelist_to_buffer(nmlfile, nml_buffer)` | `:77` | reads the whole runfile into a 4096-character buffer (`f90src/Utils/fileUtil.F90:25`); a file longer than the buffer aborts, because the stream read must end at EOF (`fileUtil.F90:143-150`, in `namelist_to_buffer`) |
| 2 | `readnamelist(...)` | `:80` | parses `/ecosim/`, `/bbgcforc/`, optional `/FixClimForc/`, `/Microbes/` (see [model_config.md](model_config.md)) |
| 3 | `mkdir -p <cwd>/<case_name>_outputs/` | `:83-87` | output directory |
| 4 | `init_timer` | `:89-92` | only if `do_timing` |
| 5 | `SetMesh(NHW,NVN,NHE,NVS)` | `:98` | reads the landscape corners from the grid file, sets `JX`, `JY`, `JZ=20` (see [grid_and_mesh.md](grid_and_mesh.md)) |
| 6 | `InitModules()` | `:100` | allocation and one-time initialisation (§2) |
| 7 | `readi(NHW,NHE,NVN,NVS)` | `:103` | site, topography and soil-profile input (`f90src/IOutils/readimod.F90:62`) |
| 8 | `write_modelconfig()` | `:105` | writes `ecosim.setup` if `disp_modelconfig` (`drivers/ecosim/EcoSIMAPI.F90:647-666`) |
| 9 | `set_sim_type()` | `:107` | startup, continue or branch from `continue_run` and `finidat` (`f90src/Modelconfig/EcoSIMConfig.F90:77-91`) |
| 10 | `get_sim_len(forc_periods,nperiods)` | `:109` | total simulated years (`f90src/Modelconfig/EcoSIMCtrlMod.F90:165-182`) |
| 11 | `frectyp%ymdhs0 = start_date` or the restart date | `:117-124` | the anchor every year-start test compares against |
| 12 | `hist_htapes_build()`, `get_clm_years()` | `:126`, `:129` | history tapes and climate-year table |
| 13 | forcing-period loop | `:140-167` | see below |
| 14 | `regressiontest` if `do_rgres` | `:169-171` | |
| 15 | `DestructEcoSIM` | `:172` | teardown (§3) |

The forcing loop is three nested loops. For each period `nn1` (`:140`) it first calls `set_ecosim_solver(NPXS(nn1),NPYS(nn1),NCYC_LITR,NCYC_SNOW)` (`:141`), then repeats the period `forc_periods(nn1*3)` times (`:143`), and inside walks the climate years `forc_periods(nn3+1)..forc_periods(nn3+2)`, forwards or backwards (`:146-150`). For each climate year it sets `frectyp%yearclm` (the forcing year) and `frectyp%yearcur` (the model calendar year, `:151-152`) and calls `AdvanceModelOneYear` (`:156`) only if the model year equals the running counter `yeari` (`:155`). So the forcing year and the model year are decoupled: a 30-year spin-up can recycle one forcing decade three times while the model calendar advances 30 years.

## 2. `InitModules` (`f90src/Main/InitEcoSIM.F90:15-59`)

| order | call | line | notes |
|---|---|---|---|
| 1 | `InitAlloc()` | `:34` | allocates every state type (§2.1) |
| 2 | `ReadPlantTraitTable()` | `:37` | only if `plant_model .and. .not. ats_cpl_mode`; the live plant-trait reader (`f90src/IOutils/PlantInfoMod.F90:1708`) |
| 3 | `units%Initailize()` | `:39` | unit-conversion singleton (`f90src/Utils/UnitMod.F90`) |
| 4 | `InitPlantDisturbance` | `:41` | calls `InitPlantFireMod` (`f90src/Plant_bgc/PlantDisturbsMod.F90:60-63`) |
| 5 | `InitUptake` | `:43` | root-uptake work arrays (`f90src/Plant_bgc/UptakesMod.F90`) |
| 6 | `initNitro` | `:45` | layered soil-BGC work arrays (`f90src/Microbial_bgc/Layers_Micmodel/SoilBGCNLayMod.F90`) |
| 7 | `InitRedist` | `:47` | `f90src/Balances/RedistMod.F90:63` |
| 8 | `InitErosion` | `:49` | `f90src/Disturbances/ErosionMod.F90:47` |
| 9 | `InitHour1(micpar%NumOfLitrCmplxs)` | `:51` | `f90src/Modelforc/Hour1Mod.F90:73` |
| 10 | `InitTranspNoSalt` | `:53` | `f90src/Transport/Nonsalt/TranspNoSaltMod.F90:50` |
| 11 | `hist_ecosim%Init(bounds)` | `:55` | history buffers (type `HistDataType`, implementations in `IOutils/HistData/` submodules) |
| 12 | `MicAPI_Init` | `:57` | microbial API containers and the microbial trait header (`f90src/APIs/MicBGCAPI.F90:60-70`) |

### 2.1 `InitAlloc` (`f90src/Ecosim_mods/InitAllocMod.F90:65-155`)

The single allocation entry point. Order matters for two calls: `InitSOMBGC` runs first (`:67`) and sizes `micpar` (litter complexes, kinetic components, functional groups), and `InitPlantMorphSize` (`:69`, body `:157-192`) then copies the grid constants and the `micpar` component indices into `pltpar` and hard-codes the plant dimensions `NumLitterGroups=5`, `MaxNumBranches=10`, `MaxNumRootAxes=10`, `NumGrowthStages=10`, `NumOfPlantMorphUnits=7`, `NMaxRootSegs=10` (`:180-185`), writing them back to the `GridConsts` module variables (`:186-191`). If `plant_model`, `InitPlantTraitTable(pltpar,NumGrowthStages,MaxNumRootAxes)` (`:71-74`) runs `InitVegPars` and allocates the trait table, and returns `NumGrowthStages` and `MaxNumRootAxes` from `pltpar` (`f90src/Modelpars/PlantBGCPars.F90:161-176`). The remaining calls allocate the grid, tracer IDs (`InitTracerIDs(salt_model)`, `:78`), canopy, chemistry, management, rates, soil, water, litter, sediment, irrigation, plant API, microbial, transport, SOM, fertiliser, traits, flags, sums, roots (`InitRootData(2)`, `:124`), forcing, fluxes, snow, history, heat, physics, numerical work space, and two new types at cb243228: `InitRadiationData` (`:146`) and `InitMLDataType` (`:148`). Salt properties (`:149`), soil warming (`:151`) and balance-check data (`:153`) close the list.

## 3. `DestructEcoSIM` (`f90src/Main/EcoSIMDesctruct.F90:10-141`)

The file name keeps its original misspelling (`EcoSIMDesctruct`). It mirrors `InitModules`/`InitAlloc`: `MicAPI_cleanup` first (`:59`), then about forty `Destruct*` calls, `DestructTranspNoSalt` only if `.not.salt_model` (`:91-93`), the new `DestructMLDataType` and `DestroyRadiationData` (`:137`, `:139`), and `CleanUpTracerIDs` last (`:140`). A new state type needs its destructor added here.

## 4. `AdvanceModelOneYear` (`drivers/ecosim/EcoSIMAPI.F90:343-571`)

### 4.1 Annual setup

| step | line | call | condition |
|---|---|---|---|
| a | `:394` | `is_first_year = frectyp%yearacc==0` | |
| b | `:401-403` | read clock stamp `ymdhs`, set `iYearCurrent` | |
| c | `:407` | `InitControlParms` (`f90src/Ecosim_mods/StartsMod.F90:732-750`) | every year: litter bulk densities, `InitSOMConsts`, `ZERO=1e-16`, `ZERO2=1e-8` |
| d | `:410-418` | `STARTS` | **only when `ymdhs(1:4)==frectyp%ymdhs0(1:4)`** |
| e | `:420-426` | `ReadPlantInfo(yearcur,yearclm,...)` | every year if `plant_model` |
| f | `:429` | `ReadClimSoilForcing(yearcur,yearclm,...)` | every year |
| g | `:434-439` | `STARTQ(NHW,NHE,NVN,NVS,1,JP)` | **only in the start year**, and `plant_model` |
| h | `:441-450` | `STARTE` | **only in the start year**, and `soichem_model` |
| i | `:453-457` | `read_soil_warming_Tref` | if `check_warming_year(iYearCurrent)` |
| j | `:459` | `DazCurrYear = etimer%get_days_cur_year()` | 365 or 366 |

The start-year test compares the year of the current clock stamp with the year of `frectyp%ymdhs0`, which is `start_date`, or the restart date on a restart (`drivers/ecosim/ecosim.F90:117-124`). STARTS, STARTQ and STARTE are therefore one-time cold-start initialisers, not annual ones. The comment beside the STARTE call (`EcoSIMAPI.F90:442-446`) and the header of `starte` (`f90src/Ecosim_mods/StarteMod.F90:43-45`) both say "every year"; the condition says otherwise. Plants are re-initialised at each planting by `StartPlants` (`f90src/Plant_bgc/InitPlantMod.F90:38-158`), called from `set_plant_flags` on the planting day (`f90src/Plant_bgc/PlantPhenolMod.F90:225`, `:256`), not by STARTQ.

### 4.2 Day loop (`:466-568`)

For `I = 1..DazCurrYear`: optional verbose toggling by `idebug_day`/`idebug_year` (`:469-473`); early return at day `LYRG` when running a regression test (`:474`); `DAY(I,...)` (`:479`, `f90src/Modelforc/DayMod.F90:46-89`); `SetAnnualAccumlators(I,...)` (`:483`, `f90src/Modelforc/YearMod.F90:38`), which zeroes the within-year cumulative diagnostics on day 1 (`YearMod.F90:53-86`). `DAY` sets solar noon from the equation of time (`DayMod.F90:72-76`), applies bio-aerosol deposition at hour 12 (`:77`), updates daily accumulators and day length (`:81`), sets the tillage mixing fraction and automatic irrigation (`:83`, `TillageandIrrigationEvents`, `:219`), and under `ldo_sp_mode` interpolates prescribed phenology (`:85`).

### 4.3 Hour loop (`:486-555`)

For `J = 1..24`:

1. On the hour equal to `frectyp%ymdhs0`, clear `lskip_loop`, and on a restart or branch read the restart file and summarise tracer masses (`:491-507`). Hours before that stamp are skipped with only a clock update (`:508-511`), which is how a restart fast-forwards to its stamp.
2. `PrepHourlyWeather(I,J,...)` (`:518`, `f90src/Modelforc/WthrMod.F90:51`): this hour's forcing, open-top-chamber and infrared warming (`WthrMod.F90:105-106`).
3. `Run_EcoSIM_one_step(yearIJ,...)` (`:522`, §5).
4. `hist_ecosim%hist_update` and `hist_update_hbuf` (`:526`, `:530`).
5. Clock update, end-of-run and restart-write tests (`:534-538`), tape wrap-up (`:542`), restart write if due (`:545-550`).

After the hour loop, `WriteBBGCFORC` if `do_bgcforc_write` (`:562-566`).

## 5. One hour: `Run_EcoSIM_one_step` (`drivers/ecosim/EcoSIMAPI.F90:37-128`)

| # | line | call | guard | then calls, in order |
|---|---|---|---|---|
| 1 | `:49` | `HOUR1` (`f90src/Modelforc/Hour1Mod.F90:85-250`) | none | landscape accumulators reset (`:106`), atmospheric tracer concentrations (`:109`), flux arrays reset (`:114`), litter properties (`:142`), soil and litter properties after disturbance (`:147`), tracer mass summary if needed (`:149`), **`BegCheckBalances` (`:151`)**, per column: diagnostics, plant-soil transfer arrays, zeroing, water-table depth `DiagWaterTBLDepz` (`:178`), chemical and solute concentrations, uptake preparation, gas solubility, soil hydraulics, active-layer depth, surface residue, litter-air tracers, optional instantaneous equilibrium (`:199`), **canopy radiation `PlantCanopyRadsModel` (`:201`)**, root-layer index floors at `NU` (`:223-235`), canopy interception (`:238`); then **`ApplyFertilizerAtNoon` (`:247`)** |
| 2 | `:56` | `WATSUB` (`f90src/HydroTherm/SoilPhys/WatsubMod.F90:86`) | none | cable warming (`:118-122`), local copies, `BeginMassCheck` (`:127`), surface-physics staging (`:130`), then `NPH` sub-cycles (`:137-171`) of surface physics, subsurface 3-D flow, boundary flow, snow redistribution, soil moisture/temperature update and **`ExitMassBalanceM` (`:169`)** |
| 3 | `:63` | `MicrobeModel` (`f90src/APIs/MicBGCAPI.F90:84-176`) | `microbial_model` (`:61`) | per column, per layer `L=0..NL` where pores exist and `L==0 .or. L>=NU`: `sumMicBiomLayL` before and after `MicBGC1Layer` → `SoilBGCOneLayer` (`:124-126`, `:191`), PAR attenuation for cyanobacteria (`:133-146`); then `DownwardMixOM` for every layer (`:162-165`); then **`SOMRemovalByDisturbance` (`:169`)** |
| 3b | `:66` | `MLDataDiag` | `lmicrobeMLdiag` | machine-learning diagnostic sampling (`f90src/ModelDiags/MLDataDiagMod.F90:39`) |
| 4 | `:73` | `PlantModel` (`f90src/APIs/PlantMod.F90:37-107`) | `plant_model .and. .not. ldo_radiation_test` (`:71`) | see §5.1 |
| 5 | `:82` | `soluteModel` (`f90src/APIs/GeochemAPI.F90:23`) | `soichem_model` (`:80`) | equilibrium chemistry |
| 6 | `:91` | `TranspNoSalt` (`f90src/Transport/Nonsalt/TranspNoSaltMod.F90:296-348`) | none | `EnterMassCheck` (`:312`), `NPH` slow sub-steps each with `NPT` fast sub-steps (`:322-338`), bubbling if `ldo_transpt_bubbling` (`:336`), **`ExitMassCheck` (`:344`)** |
| 7 | `:100` | `TranspSalt` | `salt_model` (`:98`) | |
| 8 | `:110` | `EROSION` (`f90src/Disturbances/ErosionMod.F90:62-90`) | internal: `iErosionMode` 1 or 3 | |
| 9 | `:117` | `REDIST` (`f90src/Balances/RedistMod.F90:76-156`) | none | per column, in order: `AddFlux2SurfaceResidue`, `SinkSediments`, `ModifyExWTBLByDisturbance`, `XGridTranspt`, `SnowMassUpdate`, `HandleSurfaceBoundary`, `SoilErosion`, `DiagSnowChemMass`, `LitterLayerSummary`, `UpdateTSoilVSMProfile`, `UpdateChemInSoilLays`, `SnowpackLayering`, `UpdateSoilGrids`, `UpdateOutputVars` (`:113-149`); `UpdateOutputVars` assembles NEE and the ecosystem accumulators and calls **`ApplyTillageMixing` (`:252`)** |
| 10 | `:122` | `DiagSoilGasPressure` (`f90src/ModelDiags/SoilDiagsMod.F90:31`) | none | |
| 11 | `:124` | **`EndCheckBalances`** (`f90src/ModelDiags/BalancesMod.F90:170-429`) | none | hourly water and gas-tracer closure, aborts on failure ([../balances_and_disturbances/mass_balance.md](../balances_and_disturbances/mass_balance.md)) |

### 5.1 `PlantModel` (`f90src/APIs/PlantMod.F90:37-107`)

Dynamic plants (`ldo_sp_mode=.false.`, the default): `PrepLandscapeGrazing` once (`:53`), then for every column `PlantAPISend` (`:71`), **`EnterPlantBalance` (`:73`)**, `SeedDeposition` at `J==1` (`:75-79`), `PhenologyUpdate` (`:82`, `f90src/Plant_bgc/PlantPhenolMod.F90:46`), `RootUptakes` (`:85`, `f90src/Plant_bgc/UptakesMod.F90:51`; stomata, canopy water and root water, nutrient and O2 uptake), `GrowPlants` (`:88`, `f90src/Plant_bgc/GrosubsMod.F90:61-122`), `extracts` (`:91`, `f90src/Plant_bgc/ExtractsMod.F90:34`), `ReSeedPlants` (`:93`), **`ExitPlantBalance` (`:95`)**, `PlantAPIRecv` (`:97`).

Inside `GrowPlants`, each active PFT runs `GrowOnePlant` (`GrosubsMod.F90:104`; branches via `GrowOneBranch`, roots via `RootBGCModel`, then `PlantNonstElmTransfer`, `:308-328`), then **`RemoveBiomassByDisturbance` (`:106`)**, which carries harvest, cutting, thinning, tillage effects on plants, grazing and plant fire ([../balances_and_disturbances/disturbances.md](../balances_and_disturbances/disturbances.md)), then `ResetDeadPlant` (`:109`). After the PFT loop, `Live2DeadTransformation` (`:117`) decays standing dead to surface litter.

Prescribed phenology (`ldo_sp_mode=.true.`): only `PlantUptakeAPISend`, `ROOTUPTAKES`, `extracts`, `PlantUPtakeAPIRecv` (`PlantMod.F90:60-68`); no growth, no balance check, no disturbance.

## 6. The start-year initialisers

### 6.1 `starts` (`f90src/Ecosim_mods/StartsMod.F90:73-223`)

Soil cold start: `InitControlParms` (`:93`), irradiance geometry (`:96`), grid elevation (`:99`), accumulators (`:104`), per-column grid and layer depths (`:174`, `:176`), soil state `InitSoilVars` (`:209`), snow layers (`:214`). The module also exports `set_ecosim_solver` (`:952-982`; called by the driver once per forcing period) and `startsim` (`:1017-1170`), the ATS-path equivalent, called from `f90src/ATSUtils/ATSEcoSIMInitMod.F90:147` after `SetMeshATS` (`:66`) and `set_ecosim_solver(30,10,20,20)` (`:67`).

### 6.2 `startq` (`f90src/Ecosim_mods/StartqMod.F90:34-113`)

For `NZ = NZ1Q..min(NZ2Q,NP_col)` it resets `FireReSet_pft` (`:62`) and, only for PFTs not yet active (`:63`), calls `InitShootGrowth` (`:65`; planting/harvest dates, `PPI`/`PPX`, clumping, cuticular resistances, `RootProteinCMax_pft = rNCRoot_pft*rProteinC2RootN_pft` at `:181`, `O2I` 2.10e5 for C3 and 3.96e5 otherwise at `:182-186`), `PlantLitterFractions` (`:67`), `PFTThermalAcclimation` (`:69`), `InitDimensionsandUptake` (`:71`), `InitPlantPhenoMorphoBio` (`:73`; this is where the root single-vessel axial resistance `AlphaVesselAxialResist_pft*Rax_ref*(1e-6/RootVesselRadius_pft)**4` is set, `:580`), `InitMassBalance` (`:75`), `InitRootMychorMorphoBio` (`:77`), `InitSeedMorphoBio` (`:79`), `InitPlantHeatandWater` (`:81`) and, on a cold run in the first year only, `InitStandingDead` (`:83-85`). It then sets the `ZERO4*` thresholds from the live population (`:88-90`) and zeroes arrays for unused PFT slots (`:95-109`). The leaf protein ratios are not set here; the assignments are commented out (`:178-180`).

### 6.3 `starte` (`f90src/Ecosim_mods/StarteMod.F90:39-189`)

Chemistry cold start: dissolved gas concentrations from the atmospheric columns (`:63-69`), then a loop over 366 days and the soil layers setting precipitation, irrigation and soil solute concentrations (`:71` onward, `InitSoluteConcs` `:192`, `InitialState` `:502`). Despite its header comment, it runs only in the start year (§4.1).

## 7. Compressed call tree

```
program main                                   drivers/ecosim/ecosim.F90:1
  readnamelist                                 EcoSIMAPI.F90:130
  SetMesh                                      Mesh/GridMod.F90:13
  InitModules -> InitAlloc ...                 Main/InitEcoSIM.F90:15
  readi                                        IOutils/readimod.F90:62
  loop periods / repeats / climate years       ecosim.F90:140-167
    set_ecosim_solver                          Ecosim_mods/StartsMod.F90:952
    AdvanceModelOneYear                        EcoSIMAPI.F90:343
      InitControlParms (every year)
      [start year] STARTS, STARTQ, STARTE
      ReadPlantInfo, ReadClimSoilForcing (every year)
      day loop: DAY, SetAnnualAccumlators
        hour loop: PrepHourlyWeather
          Run_EcoSIM_one_step                  EcoSIMAPI.F90:37
            HOUR1 (BegCheckBalances, radiation, fertiliser at noon)
            WATSUB (NPH sub-cycles, ExitMassBalanceM)
            MicrobeModel (SoilBGCOneLayer per layer, SOMRemovalByDisturbance)
            PlantModel (Enter/ExitPlantBalance around phenology, uptake, growth, disturbance)
            soluteModel, TranspNoSalt (Enter/ExitMassCheck), TranspSalt, EROSION
            REDIST (state update, tillage mixing at noon)
            DiagSoilGasPressure, EndCheckBalances
          history update, restart write
  DestructEcoSIM                               Main/EcoSIMDesctruct.F90:10
```

## 8. Things that are easy to get wrong

- STARTQ does not run again after the start year. A trait read by `ReadPlantInfo` each year reaches the plant through `StartPlants` at the next planting, not through STARTQ.
- `PlantModel` runs after `MicrobeModel` in the same hour, so plant uptake competes against soil solute pools already modified by the microbial step of that hour.
- `PrepHourlyWeather` precedes `HOUR1`; fertiliser is applied inside `HOUR1` at solar noon, tillage mixing inside `REDIST` at solar noon, soil fire and litter removal inside `MicrobeModel` at solar noon, and harvest inside `PlantModel` at solar noon (grazing is hourly).
- Two balance checks run inside the hour before `EndCheckBalances`: the plant balance in `PlantModel` and the water balance in `WATSUB`; the transport mass check runs at the end of `TranspNoSalt`. Any of them can end the run (see [../balances_and_disturbances/mass_balance.md](../balances_and_disturbances/mass_balance.md)).

## Calibration parameters

This page owns no plant-file or microbial-file calibration parameter. The run-control switches are tabulated in [model_config.md](model_config.md).
