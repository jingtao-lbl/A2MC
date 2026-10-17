---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `drivers/ecosim/{ecosim.F90,EcoSIMAPI.F90}`, with the time manager `f90src/Utils/ecosim_time_mod.F90`, the run controls in `f90src/Modelconfig/{EcoSIMCtrlMod,EcoSIMConfig}.F90`, and `f90src/Utils/{fileUtil,abortutils}.F90`
**Last verified:** 2026-10-15
---

# Main Standalone Driver (`ecosim.f90.x`)

The executable everyone runs is built from two files:

| File | Lines | Role |
|---|---|---|
| `drivers/ecosim/ecosim.F90` | 175 | `PROGRAM main`: command line, runfile buffer, grid and module setup, the forcing-period / year loop |
| `drivers/ecosim/EcoSIMAPI.F90` | 668 | `module EcoSIMAPI`: `readnamelist`, `AdvanceModelOneYear`, the module-private hourly orchestrator `Run_EcoSIM_one_step`, `regressiontest`, `write_modelconfig` |

`EcoSIMAPI` publishes `AdvanceModelOneYear`, `readnamelist`, `regressiontest`, `write_modelconfig`, and the two timing flags `do_timing`, `do_timing_detail` (`drivers/ecosim/EcoSIMAPI.F90:30-34`). `Run_EcoSIM_one_step` (`:37-128`) is private to the module.

## 1. Program flow (`ecosim.F90`)

| Step | What happens | Citation |
|---|---|---|
| 1 | Record a launch label for the timers | `drivers/ecosim/ecosim.F90:55` |
| 2 | `GETCWD`; if the path looks like `C:...` the run is treated as DOS: the second argument is the working directory and `PREFIX='.\\'` | `:59-73` |
| 3 | The first argument is the runfile; `namelist_to_buffer` reads it into a 4096-character buffer | `:75-77` |
| 4 | `readnamelist` parses all groups (section 2) | `:80` |
| 5 | Create `<cwd>/<case_name>_outputs/` with `mkdir -p`; it is only used by the timers | `:82-87`, `:89-92` |
| 6 | `year_ini` is the first four characters of `start_date` | `:94` |
| 7 | `SetMesh` (grid extent), `InitModules` (allocation, plant trait table, physics module init), `readi` (grid file) | `:98-103` |
| 8 | `write_modelconfig` writes `ecosim.setup` in the working directory | `:105`; `drivers/ecosim/EcoSIMAPI.F90:647-666` |
| 9 | `set_sim_type`: startup, continue (restart) or branch (section 5) | `drivers/ecosim/ecosim.F90:107` |
| 10 | `nstopyr = get_sim_len(forc_periods, nperiods)` and `etimer%update_sim_len(nstopyr)` (section 3) | `:109-111` |
| 11 | `frectyp%Init()`; on a restart `frectyp%ymdhs0` is the restart date read from `rpointer.esim`, otherwise `start_date` | `:113-124` |
| 12 | Build history tapes; load climate-year bookkeeping | `:126`, `:129` |
| 13 | Period, repeat, year loop (below) | `:140-167` |
| 14 | `regressiontest` if `do_regression_test`; `DestructEcoSIM`; close timers | `:169-173` |

`InitModules` reads the plant trait table only when `plant_model .and. .not. ats_cpl_mode` (`f90src/Main/InitEcoSIM.F90:37`). Because `readnamelist` runs first and forces `plant_model = .true.` in prescribed-phenology mode, the trait table is also read in SP mode.

The time loop:

```fortran
DO nn1=1,nperiods                                   ! drivers/ecosim/ecosim.F90:140
  call set_ecosim_solver(NPXS(NN1),NPYS(NN1),NCYC_LITR,NCYC_SNOW)
  do nn2=1,forc_periods(nn1*3)                      ! repeats of period nn1
    nn3=(nn1-1)*3
    idy=1; if(forc_periods(nn3+1)>forc_periods(nn3+2))idy=-1
    do nyr1=forc_periods(nn3+1),forc_periods(nn3+2),idy
      frectyp%yearclm=nyr1                          ! FORCING year
      frectyp%yearcur=etimer%get_curr_yearAD()      ! MODEL year
      nlend=.false.
      IGO=yeari-year_ini
      if(frectyp%yearcur==yeari) call AdvanceModelOneYear(NHW,NHE,NVN,NVS,nlend)
      if(nlend)exit
      frectyp%yearacc=frectyp%yearacc+1
      yeari=yeari+1
    end do
    if(nlend)exit
  end do
  if(nlend)exit
end do
```

The forcing year (`yearclm`) and the model year (`yearcur`) are different things. The model calendar starts at `start_date` and advances one year per call. The forcing year walks through each `forc_periods` triplet, possibly backwards (`idy = -1`), and repeats each triplet `forc_periods(3*nn1)` times. Management readers key on the forcing year, so a recycled spin-up period replays its planting, cutting and fertilizer events. `NPXS` and `NPYS` are per-period arrays of length 5 (`f90src/Modelconfig/EcoSIMCtrlMod.F90:124`), applied by `set_ecosim_solver` at the start of each period (`f90src/Ecosim_mods/StartsMod.F90:952-982`).

## 2. Reading the runfile

### 2.1 The 4096-byte buffer

`ecosim_namelist_buffer_size = 4096` (`f90src/Utils/fileUtil.F90:25`). `namelist_to_buffer` (`:125-176`) opens the runfile as an unformatted stream and reads it into one 4096-character variable (`:143`). It requires that read to end at end-of-file. If it does not (`nml_error /= -1`) it prints an I/O error and calls `abort()` (`:146-150`). A runfile of 4096 bytes or more therefore aborts before any group is parsed, with a non-zero status. After the read, every character after the last `/` in the buffer is blanked (`:155-158`), and the routine prints `Read buffer of N characters` and echoes the buffer. Long comments count against the limit, so keep runfile comments short.

### 2.2 Groups the standalone driver reads

| Group | Declared | Read | Missing-group behaviour |
|---|---|---|---|
| `/ecosim/` | `drivers/ecosim/EcoSIMAPI.F90:160-169` and `:180-182` (two `NAMELIST` statements, one group) | `:266-270` in `readnamelist`; any read error calls `endrun` | required |
| `/bbgcforc/` | `:185-186` | `:272-276`; error calls `endrun` | every shipped example has an empty `&bbgcforc /` |
| `/FixClimForc/` | `:188` | `:319-323`, only when `fixClime` (`:317`) | not read unless `fixClime` |
| `/ecosim_time/` | `f90src/Utils/ecosim_time_mod.F90:240-241` | `etimer%Init(nml_buffer,year0=year0)` (`drivers/ecosim/EcoSIMAPI.F90:290`) -> `ReadNamelist`, only if the buffer contains the text `ecosim_time` (`f90src/Utils/ecosim_time_mod.F90:261`) | defaults apply (section 3) |
| `/Microbes/` | `f90src/Modelpars/MicrobeConfigMod.F90:17-22` | `ReadMicrobeNamelist` (`drivers/ecosim/EcoSIMAPI.F90:338`; read at `f90src/Modelpars/MicrobeConfigMod.F90:41-45`) | every guild count stays 1 (`:29-39`). Run evidence: a production runfile with no `&Microbes` group runs normally. |
| `/regression_test/` | `f90src/Utils/TestMod.F90:96` | read from the runfile by unit, not from the buffer, only by `regressiontest` (`drivers/ecosim/EcoSIMAPI.F90:603`) | used only with `do_regression_test` |

### 2.3 What `readnamelist` does around the read

Before the read it overwrites most declaration defaults (`drivers/ecosim/EcoSIMAPI.F90:195-264`). After the read:

- `erosion_model = iErosionMode >= 0` (`:288`).
- `etimer%Init` reads `/ecosim_time/` with `year0` from `start_date` (`:289-290`).
- `do_rgres = do_regression_test`, `LYRG = num_of_simdays`, `lverb = lverbose` (`:298-300`).
- If `soichem_model` is false, `salt_model` is forced false (`:302-304`).
- If `ldo_radiation_test`, `ldo_sp_mode` is forced true (`:306`). If `ldo_sp_mode`, then `plant_model = .true.`, `soichem_model = .false.`, `microbial_model = .false.` (`:307-312`).
- If `plant_model` is false, `plantOM4Heat` is forced false (`:313`).
- `config_soil_warming(warming_exp)` when `len_trim(warming_exp) > 10` (`:315`); `config_fire(FireEvents)` always (`:316`).
- `/FixClimForc/` values copied into `clim_var` (`:330-335`).
- `ReadMicrobeNamelist` (`:338`).

### 2.4 `/ecosim/` member reference

78 members. "Default" is the value in effect if the runfile omits the key: the `readnamelist` assignment when there is one, otherwise the declaration initialiser. "Inert" means the value is read but nothing downstream uses it.

| Member | Default (source) | Effect / downstream use |
|---|---|---|
| `case_name` | none (`f90src/Modelconfig/EcoSIMConfig.F90:29`) | prefix of every history and restart file name |
| `prefix` | none | legacy input-path prefix; set to `.\\` on DOS (`drivers/ecosim/ecosim.F90:68`) |
| `do_regression_test` | `.false.` (`drivers/ecosim/EcoSIMAPI.F90:236`) | `do_rgres`; enables the day early-exit and `regressiontest` |
| `num_of_simdays` | `-1` (`:229`) | `LYRG`; `AdvanceModelOneYear` returns at day `LYRG` only when `do_rgres` (`:474`) |
| `lverbose` | `.false.` (`:237`) | `lverb` verbose prints |
| `num_microbial_guilds` | `1` (`:238`) | **inert**: copied to `nmicbguilds` (`:301`), unused in `drivers/ecosim/ecosim.F90`; guild counts come from `/Microbes/` |
| `transport_on` | `.true.` (`f90src/Modelconfig/EcoSIMConfig.F90:8`) | **inert**: no use outside the namelist |
| `column_mode` | `.false.` (`f90src/Modelconfig/EcoSIMConfig.F90:9`) | column (no lateral) mode switches in hydrology and transport |
| `do_instequil` | `.false.` (`:10`) | instantaneous-equilibrium option used by the transport code |
| `salt_model` | `.false.` (`drivers/ecosim/EcoSIMAPI.F90:234`) | full salt chemistry and `TranspSalt`; forced off without `soichem_model` |
| `pft_file_in` | `''` (`:244`) | plant trait table (see `../io_and_forcing/input_readers.md`) |
| `grid_file_in` | `''` (`:245`) | grid and soil file read by `readi` |
| `pft_mgmt_in` | `'NO'` (`:246`) | plant management file |
| `clm_factor_in` | `'NO'` (`:243`) | climate-change factor file |
| `clm_hour_file_in`, `clm_day_file_in` | `''` (`:247-248`) | hourly / daily climate |
| `soil_mgmt_in` | `'NO'` (`:249`) | soil management (fertilizer, tillage, irrigation) |
| `forc_periods(15)` | `0`, then `(1980,1980,1, 1981,1988,2, 1989,2008,1)` in elements 1-9 (`:226-227`) | up to 5 `(first year, last year, repeats)` triplets (section 3) |
| `NCYC_LITR`, `NCYC_SNOW` | `20`, `20` (`:204-205`) | litter and snow sub-cycles |
| `NPXS(5)`, `NPYS(5)` | `30`, `10` (`:198-199`) | per-period sub-steps per hour for water, heat and solutes, and gas cycles per `NPX` |
| `continue_run` | `.false.` (`:197`) | `.true.` makes the run a restart (`f90src/Modelconfig/EcoSIMConfig.F90:82-83`) |
| `restart_out` | `.false.` (`drivers/ecosim/EcoSIMAPI.F90:209`) | **inert**: restart cadence is set by `/ecosim_time/` |
| `lsoilCompaction` | `.false.` (`:201`) | soil compaction option |
| `LMacPoreOff` | `.false.` (`:233`) | turns macropores off |
| `finidat` | `''` (`:219`) | non-empty without `continue_run` makes a branch run (`f90src/Modelconfig/EcoSIMConfig.F90:85-88`) |
| `restartFileFullPath` | `''` (`drivers/ecosim/EcoSIMAPI.F90:220`) | restart file for branch runs |
| `brnch_retain_casename` | `.false.` (`:222`) | keep case name on branch |
| `plant_model`, `microbial_model`, `soichem_model` | `.true.` each (`:211-213`) | gate `PlantModel`, `MicrobeModel`, `soluteModel` (section 4.3) |
| `atm_ghg_in` | `''` (`:250`) | atmospheric GHG time series |
| `aco2_ppm`, `ao2_ppm`, `an2_ppm`, `ach4_ppm`, `anh3_ppm`, `arg_ppm` | `280`, `0.209e6`, `0.78e6`, `1.144`, `5e-3`, `0.00934e6` (`:251-257`) | background mixing ratios. `an2o_ppm` is defaulted (`:253`) but is **not** a member. |
| `atm_co2_fix`, `atm_n2o_fix`, `atm_ch4_fix` | `-100` (`:258-260`) | a positive value pins that gas |
| `snowRedist_model` | `.true.` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:73`) | snow redistribution |
| `disp_planttrait` | `.false.` (`drivers/ecosim/EcoSIMAPI.F90:216`; declaration `.true.` at `f90src/Modelconfig/EcoSIMCtrlMod.F90:128` is overwritten) | writes `<case>.plant_trait.desc.<year>` |
| `iErosionMode` | `-1` (`drivers/ecosim/EcoSIMAPI.F90:207`) | `erosion_model = iErosionMode >= 0`; `EROSION` tests the mode internally (`f90src/Disturbances/ErosionMod.F90:75`) |
| `grid_mode` | `3` (`drivers/ecosim/EcoSIMAPI.F90:206`) | grid connectivity mode (3 = vertical only, `f90src/Modelconfig/EcoSIMCtrlMod.F90:131`) |
| `first_topou`, `first_pft` | `.false.` (`drivers/ecosim/EcoSIMAPI.F90:262`; `f90src/Modelconfig/EcoSIMCtrlMod.F90:68`) | simulate only the first topographic unit / PFT |
| `fixWaterLevel` | `.false.` (`drivers/ecosim/EcoSIMAPI.F90:224`) | fixed water table |
| `idebug_day`, `idebug_year` | `-1` (`:202-203`) | turn on `lverb` for one day (any year if `idebug_year < 0`) (`:469-473`) |
| `ldo_sp_mode` | `.false.` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:80`) | prescribed-phenology mode (section 2.6) |
| `iverblevel` | `0` (`:108`) | verbosity level |
| `ldo_radiation_test` | `.false.` (`drivers/ecosim/EcoSIMAPI.F90:264`) | forces `ldo_sp_mode` and skips `PlantModel` (`:71`) |
| `ldo_transpt_bubbling` | `.true.` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:83`) | ebullition during transport |
| `plantOM4Heat` | `.false.` (`drivers/ecosim/EcoSIMAPI.F90:242`) | plant organic matter in the heat budget; forced off without plants |
| `micpar_file_in` | `''` (`:261`) | microbial parameter file; empty means compiled defaults |
| `iselect_plantZ` | `-1` (`:263`) | restrict planting to one PFT |
| `llignification` | `.false.` (`:214`) | root lignification option |
| `hist_nhtfrq`, `hist_mfilt`, `hist_fincl1`, `hist_fincl2`, `hist_fincl3` | history-module defaults | history tape frequency, length and added fields (see `../io_and_forcing/history_and_restart.md`) |
| `hist_yrclose` | `.false.` (`drivers/ecosim/EcoSIMAPI.F90:223`) | **inert**: no use outside the namelist |
| `lmicrobeMLdiag` | `.false.` (`:208`) | calls `MLDataDiag` after `MicrobeModel` (`:66`) |
| `do_budgets` | `.false.` (`:210`) | budget diagnostics |
| `ref_date`, `start_date` | `'18000101000000'` (`:217-218`) | `start_date` sets the model calendar start and `year_ini` |
| `do_timing`, `do_timing_detail` | `.false.` (`:195-196`) | timers write `<case>_outputs/timing/` (`f90src/Utils/timings.F90:54-65`) |
| `warming_exp` | `''` (`drivers/ecosim/EcoSIMAPI.F90:221`) | soil-warming experiment string |
| `fixClime` | `.false.` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:114`) | constant climate from `/FixClimForc/` |
| `FireEvents` | `''` (`drivers/ecosim/EcoSIMAPI.F90:225`) | fire schedule passed to `config_fire` |
| `oscal_test` | `0` (`f90src/Modelconfig/EcoSIMSolverPar.F90:25`) | floor on plant and root O2-stress scalars (`f90src/Plant_bgc/NutUptakeMod.F90:70`, `f90src/Plant_bgc/RootGasMod.F90:734`) |
| `lcoarseroot` | `.false.` (`drivers/ecosim/EcoSIMAPI.F90:215`) | woody coarse-root branch of root growth |
| `guard_floor_dying_stand` | `.false.` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:41`) | section 2.5 |
| `conserve_root_clamp` | `.false.` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:46`) | section 2.5 |

### 2.5 The two fork switches: `guard_floor_dying_stand` and `conserve_root_clamp`

Both are `EcoSIMCtrlMod` logicals appended to the second `/ecosim/` statement (`drivers/ecosim/EcoSIMAPI.F90:180-182`). A Fortran namelist read does not require every member, so a runfile that omits them keeps the `.false.` initialiser and reproduces the earlier binary's results (comment `:170-179`).

`guard_floor_dying_stand` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:41`) changes two sites. In `WithdrawNutBranchLeaves` the leaf nutrient-withdrawal divisions use `CPOOLT_div = AMAX1(CPOOLT, CPOOL_DIV_FLOOR_dying)` with `CPOOL_DIV_FLOOR_dying = 1.0e-12` (`f90src/Plant_bgc/PlantBranchMod.F90:308-312`; parameter `f90src/Modelconfig/EcoSIMCtrlMod.F90:53`). In `CheckPlantBalanceZ`, when total vegetation C is below `VEGC_BAL_FLOOR_dying = 1.0` gC m-2 (`f90src/Modelconfig/EcoSIMCtrlMod.F90:61`), the abort condition becomes the absolute test alone: `lbalC_abort = abs(balE) > 1e-6 .and. (lveg_too_small_for_relative_test .or. abs(err_rel) > 1e-3)` (`f90src/Plant_bgc/PlantBalMod.F90:874-877`). With the switch off this reduces to the original `abs(balE) > 1e-6 .and. abs(err_rel) > 1e-3`. The switch does not stop a stand dying; it changes which numerical failures abort.

`conserve_root_clamp` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:46`) is used only in `GrowFibrous1stRootAxes`. When that routine clamps a negative secondary or primary structural root pool to zero, the switch calls `ChargeRootDeficitUpAxis` to charge the uncovered deficit to the axis above (`f90src/Plant_bgc/RootMod.F90:3255`, `:3265`; routine `:3309-3345`). Off, the clamp silently creates mass, which the plant balance then sees as a residual. See `../plant_bgc/roots_and_uptake.md` for the balance bookkeeping.

### 2.6 `ldo_sp_mode`: what sets it and what it does

What sets it: the `/ecosim/` key `ldo_sp_mode` (member at `drivers/ecosim/EcoSIMAPI.F90:168`, default `.false.` at `f90src/Modelconfig/EcoSIMCtrlMod.F90:80`); `ldo_radiation_test = .true.` (`drivers/ecosim/EcoSIMAPI.F90:306`); and, under ATS, `ldo_sp_mode = pheno_bool` (`f90src/ATSUtils/ATSEcoSIMInitMod.F90:57`).

What it does in the standalone driver:

- Forces `plant_model` on and `soichem_model`, `microbial_model` off (`drivers/ecosim/EcoSIMAPI.F90:307-312`), so `soluteModel` and `MicrobeModel` never run.
- `DAY` calls `PrescribePhenologyInterp` each day (`f90src/Modelforc/DayMod.F90:85`).
- `PlantModel` takes the prescribed branch: `PlantUptakeAPISend`, `ROOTUPTAKES`, `extracts`, `PlantUPtakeAPIRecv` only. There is no growth, no phenology update and no plant balance check (`f90src/APIs/PlantMod.F90:60-68`, versus the dynamic branch `:71-97`).
- `PrescribePhenologyInterp` currently interpolates hard-coded example monthly LAI and SAI arrays (`f90src/Prescribed_pheno/PrescribePhenolMod.F90:201-202`, assigned at `:219-220`). Outside ATS it fixes `ndaysmon = 31`, `kmo = 1`, `dofmon = 1` (`:235-237`), so every day gets the same January-interpolated values. Treat SP mode as a test scaffold, not a data-driven phenology.

## 3. Run length and the calendar

`/ecosim_time/` members and defaults (`f90src/Utils/ecosim_time_mod.F90:240-256`): `delta_time` (1800 s), `stop_n` (2), `stop_option` (`'nyears'`), `rest_frq` (no default), `rest_opt` (`'never'`), `diag_frq`, `diag_opt`. `stop_option` maps `nsteps -> 1`, `ndays -> 2`, `nmonths -> 3`, `nyears -> 4`; anything else calls `endrun` (`:289-302`). Every shipped example sets `delta_time = 3600.`, which the hour loop assumes, because `update_time_stamp` is called once per hour iteration (`drivers/ecosim/EcoSIMAPI.F90:534`).

`get_sim_len` sums `(|last - first| + 1) * repeats` over five triplets; `nperiods` is always `size(forc_periods)/3 = 5` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:165-182`). Empty triplets contribute 0 years and 0 repeats. A negative total calls `endrun` (`:179-181`). `update_sim_len` sets `stop_count = min(nstopyr, stop_n)`, but only when `stop_option = 'nyears'` (`f90src/Utils/ecosim_time_mod.F90:1086-1093`). Consequences:

- A runfile with no `/ecosim_time/` group stops after 2 years.
- `stop_n` larger than the `forc_periods` total is silently reduced; smaller truncates the run.
- With `ndays` or `nmonths`, `forc_periods` does not cap the run.

The run ends when `curr_stop_count >= stop_count` (`its_time_to_exit`, `:403-417`). `update_time_stamp` increments that count on a new day, month, year or step, according to `stop_opt` (`:459-490`).

The calendar is Gregorian. `get_days_cur_year` returns 366 in leap years (`:652-658`), `update_time_stamp` updates `leap_yr` each new year (`:477-483`), and `AdvanceModelOneYear` loops `DazCurrYear = etimer%get_days_cur_year()` days (`drivers/ecosim/EcoSIMAPI.F90:459`, `:466`).

## 4. `AdvanceModelOneYear` (`drivers/ecosim/EcoSIMAPI.F90:343-571`)

### 4.1 Annual set-up, in source order

| Order | Call | Condition | Citation |
|---|---|---|---|
| 1 | `is_first_year = frectyp%yearacc == 0`; mass-balance flags `IBEGIN=1; ISTART=1; ILAST=0` | always | `:394`, `:399` |
| 2 | `InitControlParms` | every year | `:407` |
| 3 | `STARTS` (soil and grid state) | year of `frectyp%ymdhs0` only | `:410-418` |
| 4 | `ReadPlantInfo` (management; active flags come from the checkpoint) | every year if `plant_model` | `:420-426` |
| 5 | `ReadClimSoilForcing(yearcur, yearclm, ...)` | every year | `:429` |
| 6 | `STARTQ(NHW,NHE,NVN,NVS,1,JP)` (plant state) | first year and `plant_model` | `:434-439` |
| 7 | `STARTE` (soil chemistry, rain and irrigation chemistry) | first year and `soichem_model`. The inline comment says "every year"; the condition makes it first-year only | `:441-450` |
| 8 | `read_soil_warming_Tref` | if any day of this year is warmed | `:453-457` |

`STARTE` is where the soil-layer chemical initial state should be set, but at cb243228 its soil branch is unreachable on a non-restart run. See `../geochem/index.md` §5 before relying on the grid file's soil P and exchange-capacity inputs.

### 4.2 Day and hour loops

For each day `I = 1..DazCurrYear` (`:466`): set debug verbosity (`:469-473`), return early at `I = LYRG` if `do_rgres` (`:474`), then call `DAY` (daily management and disturbance, `:479`) and `SetAnnualAccumlators` (`:483`). For each hour `J = 1..24` (`:486`):

1. If the clock equals `frectyp%ymdhs0`: clear `lskip_loop`; on a restart or branch run call `restFile(flag='read')`, re-run `SetAnnualAccumlators` at `J = 1`, and call `SummarizeTracerMass` (`:491-507`).
2. If `lskip_loop` is still set, advance the clock and `cycle` (`:508-511`). `lskip_loop` starts `.true.` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:160`), so this is the fast-forward to the start or restart date. `DAY` and `SetAnnualAccumlators` still run for skipped days.
3. `PrepHourlyWeather` (`drivers/ecosim/EcoSIMAPI.F90:518`), `Run_EcoSIM_one_step` (`:522`), `hist_ecosim%hist_update` and `hist_update_hbuf` (`:526-530`).
4. `etimer%update_time_stamp()`; `nlend = its_time_to_exit()`; `rstwr = its_time_to_write_restart(nlend)`; `lnyr = its_a_new_year()` (`:534-538`).
5. `hist_htapes_wrapup(rstwr, nlend, bounds, lnyr)` (`:542`); `restFile(flag='write')` if `rstwr` (`:545-550`); exit the hour loop if `nlend` (`:554`).

After each day: skip the rest if still fast-forwarding (`:560`), write the batch BGC forcing record if `do_bgcforc_write` (`:562-566`), exit if `nlend` (`:567`).

### 4.3 Hourly physics order (`Run_EcoSIM_one_step`, `:37-128`)

| Order | Call | Gate | Citation |
|---|---|---|---|
| 1 | `HOUR1` | always | `:49` |
| 2 | `WATSUB` | always | `:56` |
| 3 | `MicrobeModel`, then `MLDataDiag` if `lmicrobeMLdiag` | `microbial_model` | `:61-67` |
| 4 | `PlantModel` | `plant_model .and. .not. ldo_radiation_test` | `:71-75` |
| 5 | `soluteModel` (geochemistry, `../geochem/`) | `soichem_model` | `:80-84` |
| 6 | `TranspNoSalt` | always | `:91` |
| 7 | `TranspSalt` | `salt_model` | `:98-102` |
| 8 | `EROSION` (no-op unless an erosion mode is set, `f90src/Disturbances/ErosionMod.F90:75`) | always | `:110` |
| 9 | `REDIST` | always | `:117` |
| 10 | `DiagSoilGasPressure`, `EndCheckBalances` | always | `:122-124` |

`PlantModel` in dynamic mode runs `EnterPlantBalance` and `ExitPlantBalance` every hour for every column (`f90src/APIs/PlantMod.F90:73`, `:95`). The latter can `endrun` (section 6).

## 5. Restart: types, files, cadence

- Run type (`set_sim_type`, `f90src/Modelconfig/EcoSIMConfig.F90:77-91`): `continue_run = .true.` gives a restart (`nsrContinue`); otherwise a non-empty `finidat` gives a branch run; otherwise a startup.
- On a restart, `get_restart_date` reads the file name from `./rpointer.esim` (`f90src/Modelconfig/EcoSIMConfig.F90:14-15`; `f90src/IOutils/RestartMod.F90:10499-10542`) and parses the date after `.r.`. An unreadable pointer file calls `endrun` (`:10519-10525`).
- File name: `./<case>.ecosim.r.<yyyy-mm-dd-sssss>.nc` (`f90src/IOutils/RestartMod.F90:10161-10162`), written by `restFile('write')` (`:88-93`).
- Cadence: `rest_opt` in `nsteps`, `nhours`, `ndays`, `nweeks`, `nmonths`, `nyears`, counted by `rest_frq` (`f90src/Utils/ecosim_time_mod.F90:321-349`). The default `'never'` writes no periodic restart, but `its_time_to_write_restart` ORs in `nlend` (`:353`), so a restart is always written when the run ends normally.

## 6. How a run ends, and the exit status

Normal end: the loops exit on `nlend`, `regressiontest` runs if requested, `DestructEcoSIM` frees memory, and the program reaches `END program main` (`drivers/ecosim/ecosim.F90:169-175`). Exit status 0.

Abnormal end through `endrun`: every overload prints `ENDRUN:` with the message and executes a bare `stop` (`f90src/Utils/abortutils.F90:80-101`, `:104-121`, `:124-153`). gfortran exits 0 for a bare `STOP`. `endrun` closes no history tape and writes no restart. Paths that reach `endrun` include:

| Trigger | Citation |
|---|---|
| `/ecosim/`, `/bbgcforc/`, `/FixClimForc/`, `/Microbes/` read error | `drivers/ecosim/EcoSIMAPI.F90:267-270`, `:273-276`, `:320-323`; `f90src/Modelpars/MicrobeConfigMod.F90:42-45` |
| `/ecosim_time/` read error or bad `stop_option` | `f90src/Utils/ecosim_time_mod.F90:264-265`, `:300-301` |
| negative simulation length | `f90src/Modelconfig/EcoSIMCtrlMod.F90:179-181` |
| any NetCDF error, including a missing variable in a bare `ncd_getvar` | `f90src/Utils/ncdio_pio.F90:463-466` (`check_ret`) |
| missing plant trait file | `f90src/Modelpars/PlantBGCPars.F90:196-198` |
| plant C, N or P balance failure | `f90src/Plant_bgc/PlantBalMod.F90:905` and the N and P aborts that follow, in `CheckPlantBalanceZ` |
| unreadable restart pointer | `f90src/IOutils/RestartMod.F90:10519-10525` |

Non-zero exits come only from `abort()` in `namelist_to_buffer` (`f90src/Utils/fileUtil.F90:150`, `:173`), `error stop 'timings: wall clock unavailable'` (`f90src/Utils/timings.F90:78`), and floating-point traps from `-ffpe-trap=invalid,zero,overflow` (`cmake/Modules/set_up_compilers.cmake:79`). Several physics routines also execute a bare `stop` after a diagnostic print, for example `f90src/Balances/RedistMod.F90:363` and `f90src/Transport/Nonsalt/TranspNoSaltSlowMod.F90:2811`, which also exit 0.

Run evidence (a site probe run on binary `09eb674a`, same `abortutils.F90` as cb243228): stdout ends with `ENDRUN:C balance error test failure in .../PlantBalMod.F90 at line 804`, the wrapper prints `rc=0`, and `sacct` reports `COMPLETED 0:0`. To decide whether a case succeeded, look for `ENDRUN:` in stdout and check that the history tape reaches the expected last time sample. Do not use the exit code.

## 7. Other public routines

`regressiontest(nmfile, case_name, NX, NY)` (`drivers/ecosim/EcoSIMAPI.F90:574-644`) writes four arrays for column `(NY,NX)` when `/regression_test/` sets `write_regression_output`: per-layer NH4 uptake (band plus non-band, both root types) of the first active PFT (`:609-625`), aqueous O2 (`:627-630`), liquid water content (`:632-635`) and soil temperature (`:637-640`) for layers 1-12. Comparison against a baseline is done outside the model.

`write_modelconfig` (`:647-666`) writes `ecosim.setup` with `microbial_model`, `plant_model`, `salt_model`, the erosion mode string and the grid mode string, when `disp_modelconfig` is true. `disp_modelconfig` is not a namelist member; it is `.true.` by declaration (`f90src/Modelconfig/EcoSIMCtrlMod.F90:129`) and only ATS sets it false.

## 8. Output files and where they land

| File | Written by | Citation |
|---|---|---|
| `./<case>.ecosim.h<tape>.<date>.nc` | history tapes | `f90src/IOutils/HistFileMod.F90:2183` |
| `./<case>.ecosim.r.<date>.nc`, `./rpointer.esim` | `restFile('write')` | `f90src/IOutils/RestartMod.F90:10161-10162` |
| `./ecosim.setup` | `write_modelconfig` | `drivers/ecosim/EcoSIMAPI.F90:656-657` |
| `./<case>.plant_trait.desc.<year>` | plant info when `disp_planttrait` | `f90src/IOutils/PlantInfoMod.F90:83-87` |
| `<cwd>/<case>_outputs/timing/*` | timers, only with `do_timing` | `f90src/Utils/timings.F90:54-65` |
| `fort.888`, `fort.889` | diagnostic writes from the plant balance and other checks | for example `f90src/Plant_bgc/PlantBalMod.F90:879` |

## Cross-references

- Runfile readers and the input files each key points to: `../io_and_forcing/input_readers.md`.
- History tapes, the producing equations of the calibration targets, and restart contents: `../io_and_forcing/history_and_restart.md`.
- Plant balance bookkeeping behind the most common `ENDRUN`: `../plant_bgc/roots_and_uptake.md`.
- What `soluteModel` does and why soil P sorption is inert on a fresh run: `../geochem/index.md`.
- ATS's replacement for this driver: `ats_coupling.md`.
