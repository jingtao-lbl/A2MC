# EcoSIM runfile options

Companion to `run.nml` in this folder. **Every value below was read from EcoSIM source**, not
inferred from the two worked cases; each row cites where. Options neither case exercises are marked
so, because "declared in the namelist" and "known to work here" are different claims.

> ### Why the options are in this file and not in `run.nml`
>
> EcoSIM reads the namelist into a **fixed 4096-byte buffer** and calls `abort()` when the read
> *fills* it without hitting EOF. A file that is too **long** fails; too short is the success path
> (`fileUtil.F90`; [[reference_ecosim_namelist_buffer_4096_bytes]]). A namelist carrying this
> reference inline would abort before the model started. `models/ecosim/backend.py` gates on the
> byte count before submitting, so the failure is caught early, but the budget is real:
> `run.nml` here is ~2.9 kB and real absolute paths add ~100 bytes each over the placeholders.
> **If you add long paths, trim comments.**

## The five namelist groups

| Group | Declared at | Purpose |
|---|---|---|
| `&ecosim` | `drivers/ecosim/EcoSIMAPI.F90:157,167` | everything: inputs, switches, time base, output |
| `&ecosim_time` | `f90src/Utils/ecosim_time_mod.F90:240` | run length, timestep, restart and diagnostic frequency |
| `&regression_test` | `f90src/Utils/TestMod.F90:96` | `cells`, `write_regression_output` |
| `&bbgcforc` | `EcoSIMAPI.F90:171` | BGC forcing dump; leave empty unless writing forcing files |
| `&FixClimForc` | `EcoSIMAPI.F90:174` | fixed synthetic climate (`airT_C`, `Wind_ms`, `vap_Kpa`, `Rain_mmhr`, `SRAD_Wm2`, `Atm_kPa`); only with `fixClime = .true.` |

## Input files: what each one carries

All paths must be **absolute**. `create_case()` repoints only `pft_file_in` (matched by basename);
every other input is used exactly as written and will not resolve from an ensemble case directory if
relative. Defaults are from `EcoSIMAPI.F90:226-245`.

| Namelist key | Contents | Default | A2MC calibration slot |
|---|---|---|---|
| `pft_file_in` | per-PFT plant traits (~123 vars: VCMX, VRNLI/VRNXI, CNLF, SLA1 …) | `''` | **primary**, `A2MC_BASE_PARAM_FILE` |
| `grid_file_in` | soil + site properties (~114 vars: CORGC/CORGN/CORGP, FC, WP, SCNV, BKDSI, PH, CEC, initial litter pools, latitude, slope, water table) | `''` | none |
| `pft_mgmt_in` | planting, harvest/cutting, fertiliser | `'NO'` | **secondary**, `A2MC_SECONDARY_PARAM_FILE` |
| `soil_mgmt_in` | tillage, soil amendments | `'NO'` | none |
| `clm_hour_file_in` | **hourly** weather forcing | `''` | forcing, not a parameter |
| `clm_day_file_in` | **daily** weather forcing (alternative to hourly; *neither worked case uses it*) | `''` | forcing |
| `atm_ghg_in` | atmospheric CO2/CH4/N2O time series | `''` | forcing |
| `clm_factor_in` | climate-change scaling factors; `'NO'` disables | `'NO'` | scenario |
| `micpar_file_in` | microbial kinetics (76 vars: RCCZ, VMXO, RMOM, GO2X, SPORC, SPOMC) | `''` | **tertiary**, `A2MC_BASE_PARAM_FILE_3` |

**`micpar_file_in = ''` does not mean "no microbial parameters".** The reader returns immediately on
an empty string (`NitroPars.F90:277`) and the model uses compiled-in constants from `initNitroPars`
(`NitroPars.F90:137`). Supplying a file *overrides* those. See [[reference_ecosim_parameter_surfaces]].

**Only the files your case needs.** `'NO'` is the documented off-switch for the management and
climate-factor inputs. A grassland with no tillage can set `soil_mgmt_in = 'NO'`.

## Time base: `forc_periods`, `start_date`, `stop_n`

`forc_periods` is an integer array of up to **five `(year0, year1, repeats)` triplets**
(`forc_periods(15)`, `EcoSIMCtrlMod.F90`). `repeats` is how many times that block of forcing years
is replayed, which is how spin-up works: there is no separate spin-up switch.

```
forc_periods = 2000, 2022, 1                 ! run 2000-2022 once  (23 yr)
forc_periods = 2000, 2009, 3, 2000, 2022, 1  ! replay 2000-2009 x3, then 2000-2022  (53 yr)
```

Three rules that bite:

1. **`stop_n` must equal the total years the triplets produce.** They are not derived from each other.
2. **Management keys on the FORCING year, not the model year** (`PlantInfoMod.F90:417`,
   `ReadManagementMod.F90:443`), so recycling replays planting, cuts and fertiliser too. That is
   usually what you want for spin-up. See [[reference_ecosim_forc_periods_and_spinup]].
3. **`start_date` is the MODEL calendar start** (`'YYYYMMDDHHMMSS'`), which is earlier than the first
   forcing year when you spin up. Set `A2MC_VALIDATION_START_YEAR` to this same year: it anchors
   record 0 of the output tape, and getting it wrong silently misattributes every year.

**EcoSIM uses a true Gregorian calendar** (366-record leap years), not a 365-day no-leap one. Never
block a tape with a fixed 365 ([[reference_ecosim_uses_real_leap_calendar]]).

## `&ecosim_time`

| Key | Meaning | Accepted values |
|---|---|---|
| `delta_time` | timestep in **seconds** | `3600.0` = hourly (both worked cases) |
| `stop_n` + `stop_option` | run length | `stop_option` ∈ `nsteps`, `ndays`, `nmonths`, `nyears` (`ecosim_time_mod.F90:290-297`) |
| `rest_frq` + `rest_opt` | restart-write frequency | `nsteps`, `nhours`, `ndays`, `nweeks`, … (`:322-335`) |
| `diag_frq` + `diag_opt` | diagnostic frequency | same vocabulary |

## Process switches

| Key | Default | Notes |
|---|---|---|
| `plant_model` | — | both cases `.true.` |
| `microbial_model` | — | both cases `.true.`; drives heterotrophic respiration |
| `soichem_model` | — | both cases `.true.`; soil chemistry |
| `salt_model` | `.false.` | *unused by either worked case* |
| `do_instequil` | `.false.` | instantaneous equilibrium; *unused* |
| `num_microbial_guilds` | `1` | *unused* |
| `snowRedist_model`, `lsoilCompaction`, `llignification`, `plantOM4Heat` | — | declared; *unused by either case* |
| `fixClime` | `.false.` | use `&FixClimForc` synthetic climate instead of a forcing file; *unused* |
| `warming_exp` | `''` | warming-experiment tag; *unused, but the obvious hook for a warming scenario* |

## Grid

`grid_mode` selects connectivity (`readimod.F90:130-145`, via `GridConectionMode`):

| Value | Meaning |
|---|---|
| `1` | 3D grid |
| `2` | 2D, north-south |
| `3` | 1D vertical column |

The **declared default is 3** (`EcoSIMCtrlMod.F90`), but **both worked cases set `1`** on a 1x1
grid, where a 3D grid of one cell is effectively a column. Follow the worked cases unless you have a
reason; an unlisted value calls `endrun`.

`npxs` / `npys` are per-period subcycle counts (`NPXS(5)`, `NPYS(5)`), and `ncyc_litr` / `ncyc_snow`
the litter and snow subcycles. Both cases use `30`/`10`/`20`/`20`. Leave them unless profiling says
otherwise.

## Output

| Key | Meaning |
|---|---|
| `hist_fincl1`, `hist_fincl2`, `hist_fincl3` | variables to ADD to tape 1, 2, 3. `fincl` **adds** to the default-active set; it does not replace it |
| `hist_nhtfrq` | frequency **per tape**, in order (`HistFileMod.F90`). `-24` = daily mean, `-1` = hourly. `hist_nhtfrq = -24, -1` gives a daily tape 1 and an hourly tape 2 |
| `hist_mfilt` | samples per file; `36500` keeps one long file |
| `hist_yrclose` | close the file each year |

Many useful variables are registered **inactive** in `HistDataType.F90` and must be named in a
`fincl` list to appear at all. A2MC injects `ECOSIM_SPEC.hist_activate` during `create_case`, so
listing them here as well is belt-and-braces rather than required.

**The tape set is a TARGET contract, not a preference.** Read `validation/targets.yaml` before
fixing `hist_nhtfrq`: a target carrying `tape: h1` and a sub-daily `reduce` (e.g. EcoSIM's
`growing_season_daytime_mean_abs`) cannot be scored at all without that tape, and nothing fails
loudly -- the ensemble runs, completes, and simply scores one target fewer. Measured 2026-09-01
while materializing a case whose namelist had been inherited from another case's `run.nml`: with
`hist_fincl2 = ''` the `Fs` target was unscoreable and the ensemble looked healthy.

**A second hourly tape is expensive.** Add one only when a target genuinely needs sub-daily
resolution (BioCON added one for a daytime-window flux); a daily tape has already averaged the diel
cycle away.

## Atmospheric composition

Baseline concentrations, all with source defaults from `EcoSIMAPI.F90:236-245`:
`aco2_ppm` 280, `ach4_ppm` 1.144, `an2o_ppm` 0.270, `ao2_ppm` 0.209e6, `arg_ppm` 0.00934e6,
`an2_ppm` 0.78e6, `anh3_ppm` 5.e-3. The `atm_co2_fix` / `atm_ch4_fix` / `atm_n2o_fix` trio defaults
to `-100`, a sentinel meaning "not fixed"; set a positive value to pin a concentration instead of
reading it from `atm_ghg_in`. *Neither worked case overrides any of these.*

## Worked examples in this repo

| Case | Namelist | Shape |
|---|---|---|
| `EcoSIM_BioCON` | `case_template/run.nml`, `run_r3_hourly.nml` | single continuous period, two output tapes (daily + hourly), 23 yr |
| `EcoSIM_Lusignan` | `case_template/run_spinup.nml` | **two `forc_periods` triplets**: 10 yr recycled spin-up then 18 yr production, 28 yr total, single daily tape |

Read `run_spinup.nml` if you need spin-up; it is the shorter and more instructive of the two.
