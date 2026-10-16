---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/Modelconfig/`, `f90src/Modelpars/` (structure and entry points), and the run-control namelist read in `drivers/ecosim/EcoSIMAPI.F90::readnamelist`
**Last verified:** 2026-10-15
---

# Model configuration and parameter modules

`f90src/Modelconfig/` holds run-control state (what an operator sets in the runfile), compile-time sizes and integer enumerations. `f90src/Modelpars/` holds the scientific parameter blocks and the two global parameter objects. This page documents every member of the `/ecosim/` namelist with its effective default and where it is read and used, then summarises the two directories.

## 1. How the runfile is read

The driver reads the whole runfile into a 4096-character buffer (`f90src/Utils/fileUtil.F90:25`; `namelist_to_buffer`, `:125-170`), aborting if the file does not end inside the buffer (`:143-150`). `readnamelist` (`drivers/ecosim/EcoSIMAPI.F90:130-340`) then:

1. **re-assigns most switches** to fixed values (`:195-264`) before reading, so the effective default of a switch listed there is the value assigned there, not its module initialiser;
2. reads `/ecosim/` (`:266-270`; both namelist statements `:160-169` and `:180-182` belong to the same group) and `/bbgcforc/` (`:272-276`); **a missing group is a fatal error**, so every runfile must carry `&bbgcforc ... /` even if empty;
3. applies post-read couplings: `erosion_model = iErosionMode>=0` (`:288`); the clock is initialised from `start_date` and the buffer (`:289-290`, which reads `/ecosim_time/` if present, `f90src/Utils/ecosim_time_mod.F90:240-262`); `salt_model` is forced off when `soichem_model` is off (`:302-304`); `ldo_radiation_test` forces `ldo_sp_mode` (`:306`); `ldo_sp_mode` forces `plant_model=.true.`, `soichem_model=.false.`, `microbial_model=.false.` (`:307-312`); `plantOM4Heat` is forced off without plants (`:313`);
4. configures warming if `len_trim(warming_exp)>10` (`:315`) and fire from `FireEvents` (`:316`);
5. reads `/FixClimForc/` only if `fixClime` (`:317-336`);
6. reads `/Microbes/` (`:338`, `f90src/Modelpars/MicrobeConfigMod.F90:12-47`), which is also fatal when absent (`:41-45`).

A Fortran namelist read leaves unlisted members untouched, so a runfile written before a switch existed runs with that switch at its default. This is how the two default-off fix switches added on this branch keep old runfiles bit-for-bit unchanged (comment at `EcoSIMAPI.F90:170-179`).

## 2. Every `/ecosim/` member

"Effective default" is the value in force when the runfile omits the member. "Set" is where that default comes from. Declarations are in `EcoSIMCtrlMod` (`f90src/Modelconfig/EcoSIMCtrlMod.F90`) unless stated.

### 2.1 Process switches

| member | effective default | set at | where it acts (routine) | what it does |
|---|---|---|---|---|
| `plant_model` | `.true.` | `EcoSIMAPI.F90:211` | `Run_EcoSIM_one_step` `:71`; `AdvanceModelOneYear` `:420`, `:434`; `InitAlloc` (`InitAllocMod.F90:71`); `InitModules` (`InitEcoSIM.F90:37`) | enables plant trait loading, STARTQ, and the hourly `PlantModel` |
| `microbial_model` | `.true.` | `:213` | `Run_EcoSIM_one_step` `:61` | enables `MicrobeModel` (which also runs soil fire and litter removal) |
| `soichem_model` | `.true.` | `:212` | `Run_EcoSIM_one_step` `:80`; `AdvanceModelOneYear` `:441` | enables `soluteModel` and STARTE; off forces `salt_model` off |
| `salt_model` | `.false.` | `:234` | `Run_EcoSIM_one_step` `:98`; `hour1` (`Hour1Mod.F90:118`); `InitTracerIDs`; `RedistMod`, `RunoffBalMod`, `GeochemAPI` (many) | salt tracer set and `TranspSalt` |
| `snowRedist_model` | `.true.` | module only (`EcoSIMCtrlMod.F90:73`) | `watsub` (`WatsubMod.F90:155`); `RunSurfacePhysModelM` (`SurfPhysMod.F90:1641`) | snow redistribution between columns |
| `iErosionMode` | `-1` | `:207` | `erosion` (`ErosionMod.F90:75`); `hour1` (`Hour1Mod.F90:172`); `SoilLayerDynMod`, `RedistMod`, `LateralTranspMod`, `ErosionBalMod` | -1 none, 0 freeze-thaw elevation, 1 + erosion, 2 + SOM change, 3 all (`ElmIDMod.F90:20-24`); `erosion_model = iErosionMode>=0` gates soil relayering (`UpdateSoilGrids`, `SoilLayerDynMod.F90:99`) |
| `grid_mode` | `3` | `:206` | `readsiteNC` (`readimod.F90:323`, copied to `FlowDirIndicator_col`) | lateral connectivity of the grid; 3 = vertical only |
| `column_mode` | `.false.` | `EcoSIMConfig.F90:9` (module only) | `SetMesh` (`GridMod.F90:103`); `readi` (`readimod.F90:84`); `erosion` (`ErosionMod.F90:88`) | no halo cells and no boundary erosion |
| `fixWaterLevel` | `.false.` | `:224` | `watsub` (`WatsubMod.F90:116`, `:242` and others); `UpdateTSoilVSMProfile` (`RedistMod.F90:813`); `EndCheckBalances` (`BalancesMod.F90:201`, `:218`) | holds the water table fixed and drops boundary water terms from the balance |
| `LMacPoreOff` | `.false.` | `:233` | `Subsurface3DInternalFlowM` (`WatsubMod.F90:747`) | turns off macropore lateral flow |
| `lsoilCompaction` | `.false.` | `:201` | `GrowRootMycoAxes` (`RootMod.F90:1574`, `:1592`) | when off, root elongation water factors are 1 |
| `plantOM4Heat` | `.false.` | `:242` | `UpdateTSoilVSMProfile` (`RedistMod.F90:821`, `:858`); `WatsubMod.F90:494`, `:1347`, `:2594` | counts plant organic matter in soil heat capacity |
| `do_instequil` | `.false.` | `:241` | `hour1` (`Hour1Mod.F90:199`) | forces gas-aqueous equilibrium each hour |
| `ldo_transpt_bubbling` | `.true.` | module only (`:83`) | `TranspNoSalt` (`TranspNoSaltMod.F90:336`) | ebullition during transport |
| `ldo_sp_mode` | `.false.` | module only (`:80`) | `PlantModel` (`PlantMod.F90:52`, `:60`); `day` (`DayMod.F90:85`); `RootUptakes`, `ExtractCanopyFluxes`, `CanopyConditionModel`, `PlantAPICanMSend` | prescribed ("satellite") phenology, §4 |
| `ldo_radiation_test` | `.false.` | `:264` | `Run_EcoSIM_one_step` `:71`; `SurfaceRadiation` (`SurfaceRadiationMod.F90:545`, `:593`) | radiation-only test; forces `ldo_sp_mode` |
| `llignification` | `.false.` | `:214` | `SecondaryGrowthZone` (`RootMod.F90:3540`, `:3724`, `:3742`) | root lignification option; note `SecondaryGrowthZone`'s only call is commented out (`RootMod.F90:3218`), so this switch has no effect at cb243228 |
| `lcoarseroot` | `.false.` | `:215` | `StagePlantForGrowth` (`GrosubsMod.F90:520`); `ShootRootElmTransfer` (`PlantNonstElmDynMod.F90:464`); `RootSoilGasExchange` (`RootGasMod.F90:251`); `RootMod.F90:502`, `:830`, `:1068`, `:1641` | coarse (medium-size) woody root pool |
| `guard_floor_dying_stand` | `.false.` | module only (`:41`) | `WithdrawNutBranchLeaves` (`PlantBranchMod.F90:309`); `CheckPlantBalanceZ` (`PlantBalMod.F90:850-852`) | floors the C-pool divisor at `CPOOL_DIV_FLOOR_dying = 1e-12` gC (`EcoSIMCtrlMod.F90:53`) and skips the relative C-balance test when total vegetation C < `VEGC_BAL_FLOOR_dying = 1.0` gC/m2 (`:61`); the absolute test `abs(balE)>1e-6` still applies |
| `conserve_root_clamp` | `.false.` | module only (`:46`) | `GrowFibrous1stRootAxes` (`RootMod.F90:3255`, `:3265`) | when a negative structural root pool is clamped by `AZMAX1`, charges the uncovered deficit up the axis with `ChargeRootDeficitUpAxis` (`RootMod.F90:3309-3345`) instead of discarding it |
| `oscal_test` | `0.0` | `EcoSIMSolverPar.F90:25` | `PlantNutientO2Uptake` (`NutUptakeMod.F90:70`); `RootSoilGasExchange` (`RootGasMod.F90:734`) | floor on the plant and root O2 limitation factors |

### 2.2 Atmosphere and forcing

| member | effective default | set at | where it acts | notes |
|---|---|---|---|---|
| `aco2_ppm`, `ach4_ppm`, `ao2_ppm`, `an2_ppm`, `anh3_ppm`, `arg_ppm` | 280, 1.144, 0.209e6, 0.78e6, 5e-3, 0.00934e6 | `:251-257` | `readsiteNC` (`readimod.F90:315-321`) | initial atmospheric mixing ratios; `an2o_ppm` (0.270, `:253`) and `ah2_ppm` (0.55, module) are used (`readimod.F90:319`, `:347`) but are not namelist members |
| `atm_co2_fix`, `atm_ch4_fix`, `atm_n2o_fix` | -100 | `:258-260` | `GetAtmGts` (`ClimReadMod.F90:946`, `:963-978`) | a positive value holds that gas fixed; otherwise the `atm_ghg_in` time series is used |
| `atm_ghg_in` | `''` | `:250` | `GetAtmGts` (`ClimReadMod.F90:943`) | GHG time-series file |
| `fixClime` | `.false.` | module only (`:114`) | `readnamelist` `:317`; `ReadClimSoilForcing` (`readsmod.F90:169`); `CalcRadiation` (`WthrMod.F90:308`) | constant climate from `/FixClimForc/` |
| `warming_exp` | `''` | `:221` | `config_soil_warming` (`EcosysWarmingMod.F90:198`) | warming experiment string |
| `FireEvents` | `''` | `:225` (local) | `config_fire` (`FireMod.F90:24`) | `YYYY/plantvar,soilvar;...` |

### 2.3 Input files

| member | effective default | read by |
|---|---|---|
| `pft_file_in` | `''` (`:244`) | `InitVegPars` (`PlantBGCPars.F90:192-202`); `ReadPlantTraitTable` (`PlantInfoMod.F90:1715`) |
| `pft_mgmt_in` | `'NO'` (`:246`) | `ReadPlantManagementNC` (`PlantInfoMod.F90:407-409`), `ReadPlantInfoNC` (`:1518-1531`), `ReadFire` (`ReadManagementMod.F90:573`); the guards test `len_trim==0`, so the default `'NO'` is treated as a file name |
| `grid_file_in` | `''` (`:245`) | `SetMesh` (`GridMod.F90:42`); `readi` (`readimod.F90:78`) |
| `clm_hour_file_in`, `clm_day_file_in` | `''` (`:247-248`) | `ClimReadMod.F90:727`, `:793`, `:1010-1024` |
| `soil_mgmt_in` | `'NO'` (`:249`) | `ReadManagementFiles` (`ReadManagementMod.F90:435`), `ReadFire` (`:541`); fire requires it (`FireMod.F90:91-92`) |
| `clm_factor_in` | `'NO'` (`:243`) | `ReadClimateCorrections` (`readsmod.F90:268-272`) |
| `micpar_file_in` | `''` (`:261`) | `ReadPars` (`NitroPars.F90:280-282`); empty means compiled defaults |

### 2.4 Clock, solver, restart and output

| member | effective default | set at | where it acts |
|---|---|---|---|
| `forc_periods(15)` | `(/1980,1980,1,1981,1988,2,1989,2008,1,0,...)/` | `:226-227` | `get_sim_len`, driver loops (`ecosim.F90:109`, `:140-167`); triplets (first year, last year, repeats) |
| `NPXS(5)`, `NPYS(5)` | 30, 10 for every period | `:198-199` | `set_ecosim_solver` (`StartsMod.F90:960-965`): `NPH=NPX`, `NPT=NPY`, `NPG=NPH*NPT` |
| `NCYC_LITR`, `NCYC_SNOW` | 20, 20 | `:204-205` | `set_ecosim_solver` (`StartsMod.F90:967-968`): `NPR`, `NPS` |
| `start_date`, `ref_date` | `'18000101000000'` | `:217-218` | clock year (`:289-290`); `frectyp%ymdhs0` (`ecosim.F90:123`) |
| `continue_run` | `.false.` | `:197` | `set_sim_type` (`EcoSIMConfig.F90:82`) |
| `finidat`, `restartFileFullPath` | `''` | `:219-220` | `set_sim_type` (`EcoSIMConfig.F90:85`); restart lookup (`RestartMod.F90:9836-9865`) |
| `brnch_retain_casename` | `.false.` | `:222` | `RestartMod.F90:9875` |
| `hist_nhtfrq(6)`, `hist_mfilt(6)` | `(/0,-24,...)/`, `(/1,30,...)/` | `HistFileMod.F90:48`, `:51` | tape frequency and samples (`HistFileMod.F90:733-734`) |
| `hist_fincl1`, `hist_fincl2`, `hist_fincl3` | blank | `HistFileMod.F90:66-70` | added fields per tape (`HistFileMod.F90:790-792`) |
| `case_name`, `prefix` | none | dummy arguments | output directory (`ecosim.F90:83-87`); `PREFIX` for legacy text forcing (`ClimReadMod.F90:602`) |
| `do_timing`, `do_timing_detail` | `.false.` | `:195-196` | `f90src/Utils/timings.F90` profiling ([utilities.md](utilities.md)) |
| `lverbose` | `.false.` | `:237` | copied to `lverb` (`:300`): trace output from `PrintInfo` |
| `idebug_day`, `idebug_year` | -1, -1 | `:202-203` | verbose output on one day (`AdvanceModelOneYear` `:469-470`) |
| `iverblevel` | 0 | module only (`:108`) | extra balance diagnostics (`BalancesMod.F90:231`, `:323`; transport mass checks); does not change any abort threshold |
| `disp_planttrait` | `.false.` (module says `.true.`, `:128`) | `:216` | trait listing (`readq`, `PlantInfoMod.F90:83`, `:681`, `:855`) |
| `iselect_plantZ` | -1 | `:263` | `readplantinginfo` (`PlantInfoMod.F90:197`): plant only PFT `iselect_plantZ` when > 0 |
| `first_topou`, `first_pft` | `.false.` | `:262`; module (`:68`) | `SetMesh` (`GridMod.F90:80`), readers; `ReadPlantInfoNC` (`PlantInfoMod.F90:1615`) |
| `lmicrobeMLdiag` | `.false.` | `:208` | `MLDataDiag` call (`EcoSIMAPI.F90:66`); history registration (`HistRegisterColumn.F90:18`) |
| `do_regression_test`, `num_of_simdays` | `.false.`, -1 | `:236`, `:229` | `do_rgres` (`:298`); `LYRG` stop day (`:299`, `:474`) |

### 2.5 Members that do nothing at cb243228

| member | evidence |
|---|---|
| `transport_on` | declared `EcoSIMConfig.F90:8`; no reader anywhere in `f90src/` or `drivers/ecosim/` |
| `restart_out` | only assigned (`EcoSIMAPI.F90:209`); restart writes are scheduled by `etimer%its_time_to_write_restart` (`:537`) |
| `hist_yrclose` | only assigned (`EcoSIMAPI.F90:223`; declared `EcoSIMCtrlMod.F90:120`) |
| `num_microbial_guilds` | returned as `nmicbguilds` (`EcoSIMAPI.F90:301`) and never used by the driver (`ecosim.F90:80`); guild counts come from `/Microbes/` |
| `do_budgets` | its only use is an empty `if (do_budgets) then; end if` (`RestartMod.F90:10431-10432`, in `restFile_dimset`) |
| `llignification` | acts only inside `SecondaryGrowthZone`, which has no live caller (§2.1) |

## 3. The other namelist groups

- `/bbgcforc/` (`EcoSIMAPI.F90:185-186`): `do_bgcforc_write`, `do_year`, `do_doy`, `laddband`, `do_layer`, `bgc_fname` (defaults `:230-240`); writes forcing for the box soil-BGC driver (`WriteBBGCFORC`, `EcoSIMAPI.F90:562-566`). Mandatory group.
- `/FixClimForc/` (`:188`): `airT_C`, `Wind_ms`, `vap_Kpa`, `Rain_mmhr`, `SRAD_Wm2`, `Atm_kPa`, read only when `fixClime`.
- `/Microbes/` (`MicrobeConfigMod.F90:17-22`): eleven `NumGuild_*` counts, each reset to 1 before the read (`:29-39`). Mandatory group.
- `/ecosim_time/` (`ecosim_time_mod.F90:240-241`): `delta_time` (default 1800 s), `stop_n`, `stop_option`, `rest_frq`, `rest_opt`, `diag_frq`, `diag_opt`; read only if the string `ecosim_time` occurs in the buffer (`:261`).

## 4. Prescribed phenology (`ldo_sp_mode`)

With `ldo_sp_mode=.true.` the plant model runs only uptake and flux extraction (`PlantMod.F90:60-68`), and `day` calls `PrescribePhenologyInterp` every day (`DayMod.F90:85`). That routine prescribes LAI and SAI from a twelve-month example table hard-coded in the routine (`f90src/Prescribed_pheno/PrescribePhenolMod.F90:201-202`) and, when `irootType_col>0`, sets root C and length per layer from the Jackson et al. (1997) beta profile in `SetRootProfileZ` (`:300-301`; table `beta(10)` at `:345`; `CumRootFrac = 1 - beta**(100*depth)` at `:353`, `:359`). `irootType_col` defaults to 1 (boreal forest; `f90src/Ecosim_datatype/RootDataType.F90:180`) and is set from ATS on the coupled path (`f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:275`). The local `irootType=1` (`PrescribePhenolMod.F90:211`) feeds only a commented-out call (`:295`). The call passes the whole 3-D array `CumDepz2LayBottom_vr` (lower bound 0) to the explicit-shape dummy `tmp_cdepthz(JZ)` (`:301`, `:342`), so the profile reads layer-0 depth of column (1,1) as layer 1: it is shifted one layer and ignores the current column. None of this runs in the default dynamic mode, where root vertical distribution is prognostic (root growth in `RootMod`).

## 5. `Modelconfig/` files

- `EcoSIMCtrlMod.F90` (185 lines): the switches above, the two dying-stand floors (`:53`, `:61`), file names, `etimer` (`:111`), `pft_nfid` (`:110`), the forcing record `frectyp` (`:133-146`) and `get_sim_len` (`:165-182`), which sums `(abs(last-first)+1)*repeats` over the `forc_periods` triplets and aborts if negative (`:179-181`).
- `EcoSIMConfig.F90` (100 lines): `transport_on`, `column_mode`, `do_instequil`, `brnch_retain_casename` (`:8-11`); compile-time sizes `NumDeadMicrbCompts=2`, `NumLiveMicrbCompts=3`, `jskenc=4`, `jskenp1=5`, `jcplxc=5`, `jcplxcm1=4`, `NumMicbHFunGrupsPerCmplx=8`, `NumMicbAFunGrupsPerCmplx=6` (`:18-25`); restart mode `nsrest` with `nsrStartup=0`, `nsrContinue=1`, `nsrBranch=2` (`:40-43`); `is_restart`, `is_branch`, `set_sim_type` (`:77-91`), `is_cold_run` (`:94-99`).
- `EcoSIMSolverPar.F90` (26 lines): time steps `dts_wat`, `dts_sno`, `dt_watvap`, `dts_HeatWatTP`, `dt_GasCyc`, `dts_gas` and cycle counts `NPH`, `NPT`, `NPG`, `NPR`, `NPS` (`:10-24`), set by `set_ecosim_solver` (`StartsMod.F90:952-982`) as `dts_HeatWatTP = 0.99999/NPH`, `dts_gas = 0.99999/NPG`, `dts_wat = min(1, 10*dts_HeatWatTP)*0.99999` (`:969-977`).
- `ElmIDMod.F90` (221 lines): element ids `ielmc=1`, `ielmn=2`, `ielmp=3` (`:8-11`), erosion modes (`:20-24`), irrigation triggers (`:26-27`), harvest organ ids `iplthvst_leaf..stdead` (`:42-45`), `ic4_photo=4`, `ic3_photo=3` (`:47-48`), fertiliser codes (`:50-75`), root types `ipltroot=1`, `imycorrhz=2` (`:98-99`), `jharvtyp_*` (`:106-108`), `iharvtyp_none..herbivo` 0-6 (`:110-116`), `iplt_annual=0`, `iplt_perennial=1` (`:118-119`), phenology types (`:158-161`), `itill_rmlitr=21`, `itill_fire=22` (`:177-178`), `iHarvst_pft=1`, `iHarvst_col=2` (`:179-180`).
- `TracerIDMod.F90` (409 lines): fixed gas ids `idg_CO2=1 .. idg_NH3=8` (`:13-20`); `InitTracerIDs(lsalt_model)` (`:170-402`) assigns the banded NH3 pseudo-gas `idg_NH3B=idg_NH3+1` (`:183`) and all solute, salt, precipitate and exchangeable ids sequentially; `CleanUpTracerIDs` (`:404-408`).

## 6. `Modelpars/` files

- `EcoSiMParDataMod.F90` (9 lines): the two global objects `pltpar` (type `plant_bgc_par_type`) and `micpar` (type `MicParType`) (`:7-8`).
- `PlantBGCPars.F90` (322 lines): module-level plant constants (for example `Rax_ref = 7.11e11` MPa h m-4, `:120`), the type `plant_bgc_par_type` (`:126-156`), `InitPlantTraitTable` (`:161-176`) and `InitVegPars` (`:179`), which reads the trait-file dimensions and sets the litter group ids `inonstruct=0 .. icwood=5` (`:205-210`).
- `MicBGCPars.F90` (568 lines): `MicParType` (`:29-118`) with `Init` (`:123`), `SetPars` (`:265`), `Initallocate` (`:418`), `DestructMicBGCPar` (`:497`).
- `NitroPars.F90` (371 lines): microbial kinetic constants; `initNitroPars` (`:139-266`, called from `MicBGCFGMod.F90:68`) sets defaults, including the fire emission factors `EFIRE(2,21:22)` (`:121`, `:264`), and calls `ReadPars` (`:269`), which reads `micpar_file_in` when given (`:280-282`).
- `MicrobeConfigMod.F90` (49 lines): `/Microbes/` reader.
- `ChemTracerParsMod.F90`, `SoluteParMod.F90`, `TracerPropMod.F90`: diffusivities and solubilities, equilibrium constants, and gas property functions (`gas_solubility` `:21`, `GramPerHr2umolPerSec` `:55`, `GasSechenovConst` `:81`, `MolecularWeight` `:125`).

## Calibration parameters

This page owns no plant-file or microbial-file calibration parameter; the parameter objects it describes are filled by readers documented in the plant and microbial sections. The run-control switches in §2 are model configuration, not calibration levers, except that `guard_floor_dying_stand` and `conserve_root_clamp` change which runs complete and how root mass is conserved (see [../plant_bgc/roots_and_uptake.md](../plant_bgc/roots_and_uptake.md)).
