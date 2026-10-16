---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/IOutils/` (including `HistData/`), `f90src/Modelforc/`, `drivers/ecosim/{ecosim,EcoSIMAPI}.F90`, parameter readers in `f90src/Modelpars/NitroPars.F90`
**Last verified:** 2026-10-15
---

# I/O and Forcing: Overview

EcoSIM's input/output and forcing code lives in two source directories plus the driver:

- `f90src/IOutils/` reads every input file (grid, plant parameters, plant and soil management, climate, atmospheric GHGs), writes the history tapes and restart files, and holds the history data container, now split into Fortran submodules under `f90src/IOutils/HistData/`.
- `f90src/Modelforc/` turns the loaded forcing into hourly column fields: annual and daily resets, daily-to-hourly disaggregation, radiation partitioning, the hourly state reset, and bioaerosol deposition.
- `drivers/ecosim/` reads the runfile namelist and runs the year, day and hour loops that call both.

Detail pages: `input_readers.md` (namelist, every reader, the calibration-parameter reader map), `forcing.md` (climate, GHG and weather pipeline), `history_and_restart.md` (history tapes, calibration-target producing chains, restart).

## Source files at a glance

### `f90src/IOutils/`

| File | Lines | Purpose |
|---|---|---|
| `readimod.F90` | 1078 | `readi` (`:62`): reads `grid_file_in`, site scalars (`readsiteNC`, `:195`) and per-topounit soil profile (`readTopoNC`, `:367`) |
| `readsmod.F90` | 377 | `ReadClimSoilForcing` (`:83`): yearly climate, climate-correction, fire, soil-management and GHG dispatch |
| `ClimReadMod.F90` | 1119 | climate NetCDF (`ReadClimNC`, `:696`), ASCII weather (`ReadClim`, `:583`), GHGs (`GetAtmGts`, `:926`), forcing-type selection (`get_forc_step_type`, `:1036`), soil-warming reference (`read_soil_warming_Tref`, `:1064`) |
| `PlantInfoMod.F90` | 1909 | plant parameter table (`ReadPlantTraitTable`, `:1708`), per-PFT trait copy (`SetPlantTraits`, `:696`), plant management (`ReadPlantManagementNC`, `:386`); also the uncalled `ReadPlantTraitsNC` (`:540`) |
| `ReadManagementMod.F90` | 686 | soil management (`ReadManagementFiles`, `:411`): tillage, fertiliser, irrigation; fire (`ReadFire`, `:526`) |
| `MicrobeInfoMod.F90` | 19 | stub; empty `WriteMicrobeTraits` (`:15`). The microbial file is read by `f90src/Modelpars/NitroPars.F90` |
| `HistFileMod.F90` | 2976 | history tape engine: field registry, accumulation, file creation and write, history restart |
| `HistDataType.F90` | 752 | `histdata_type` declaration (`:9`), singleton `hist_ecosim` (`:670`), submodule interfaces, `init_hist_data` (`:737`) |
| `HistData/*.F90` | 4982 in 11 files | submodules that allocate, register and fill history buffers (`history_and_restart.md` §2) |
| `RestartMod.F90` | 10543 | checkpoint read and write (`restFile`, `:70`) |
| `restUtilMod.F90` | 1935 | `restartvar`, `cpcol`, `cppft` overloads |
| `bhistMod.F90` | 468 | multi-clock writer used by the box and aquachem drivers |
| `ForcWriterMod.F90` | 286 | one-shot batch soil-BGC dump (`WriteBBGCFORC`, `:33`) |

### `f90src/Modelforc/`

| File | Lines | Purpose |
|---|---|---|
| `YearMod.F90` | 142 | `SetAnnualAccumlators` (`:38`): zeroes year-to-date counters on day 1 |
| `DayMod.F90` | 309 | `day` (`:46`): solar noon, bioaerosol deposition, daily accumulators and disaggregation coefficients, tillage and automatic irrigation |
| `Hour1Mod.F90` | 1741 | `hour1` (`:85`): hourly resets, balance bracket start, soil diagnostics, canopy radiation, noon fertiliser |
| `WthrMod.F90` | 577 | `PrepHourlyWeather` (`:51`): hourly weather from daily or hourly data, warming, radiation partitioning |
| `DepositionMod.F90` | 100 | `ApplyBioAerosol` (`:26`): organic C and microbes from dry deposition into fine litter (new since 2dea74d9) |

## Input pipeline

| Namelist key | File content | Reader | Disable token |
|---|---|---|---|
| `grid_file_in` | site, boundary conditions, grid, soil profile, surface residue, optional aerosol fractions | `readi` (`f90src/IOutils/readimod.F90:78`), once | required |
| `pft_file_in` | plant trait table, one record per PFT key (4-character code plus 2-digit Koppen zone) | `ReadPlantTraitTable` (`f90src/IOutils/PlantInfoMod.F90:1715`), once at init | `''` |
| `pft_mgmt_in` | PFT names per topounit, planting records, cut/harvest/grazing events, plant fire | `ReadPlantInfoNC` and `ReadPlantManagementNC` (`f90src/IOutils/PlantInfoMod.F90:1531`, `:409`), yearly | `''` only; the default `'NO'` aborts with `plant_model` on |
| `clm_hour_file_in`, `clm_day_file_in` | hourly or daily weather, precipitation chemistry, optional `PATM`, `XRADH`, `DRYDEPOC` | `ReadClimNC` (`f90src/IOutils/ClimReadMod.F90:696`), when the forcing year changes | `''` |
| `clm_factor_in` | monthly climate-change factors | `ReadClimateCorrections` (`f90src/IOutils/readsmod.F90:252`), yearly | `'NO'`; read but never applied |
| `soil_mgmt_in` | tillage, fertiliser and irrigation schedules, soil fire | `ReadManagementFiles` (`f90src/IOutils/ReadManagementMod.F90:411`), yearly | `'NO'` |
| `atm_ghg_in` | monthly CO2, CH4, N2O | `GetAtmGts` (`f90src/IOutils/ClimReadMod.F90:926`), yearly; January value applied | required |
| `micpar_file_in` | microbial kinetic parameters | `ReadPars` (`f90src/Modelpars/NitroPars.F90:269`), once | `''` (compiled defaults) |

The runfile itself is read into a 4096-byte buffer (`f90src/Utils/fileUtil.F90:25`); a longer runfile aborts in `namelist_to_buffer` (`:146-150`). See `input_readers.md` §1.

## Output pipeline

| Channel | Writer | Configured by |
|---|---|---|
| history tapes (up to 6, at most 3 configurable from the runfile) | `hist_htapes_wrapup` (`f90src/IOutils/HistFileMod.F90:1660`) | `hist_nhtfrq`, `hist_mfilt`, `hist_fincl1-3`, `hist_yrclose` in `/ecosim/` (`drivers/ecosim/EcoSIMAPI.F90:180`) |
| state restart | `restFile('write')` (`f90src/IOutils/RestartMod.F90:70`) | `rest_opt`, `rest_frq` in `/ecosim_time/` |
| history restart | `hist_restart_ncd` (`f90src/IOutils/HistFileMod.F90:2189`) | written with each state restart |
| batch soil-BGC dump | `WriteBBGCFORC` (`f90src/IOutils/ForcWriterMod.F90:33`) | `/bbgcforc/` |

## Time loop and where each piece runs

The main program reads the namelist (`drivers/ecosim/ecosim.F90:77-80`), initialises modules including the plant trait table and the microbial parameters (`InitModules`, `:100`), reads the grid (`readi`, `:103`), then loops over forcing periods and years (`:140-167`). Each year `AdvanceModelOneYear` (`drivers/ecosim/EcoSIMAPI.F90:343`) runs:

| Order | Call | Citation |
|---|---|---|
| yearly | `ReadPlantInfo`, then `ReadClimSoilForcing`, then `STARTQ` in the first year | `drivers/ecosim/EcoSIMAPI.F90:424`, `:429`, `:437` |
| daily | `DAY`, then `SetAnnualAccumlators` | `:479`, `:483` |
| hourly | `PrepHourlyWeather` | `:518` |
| hourly | `Run_EcoSIM_one_step`: `HOUR1`, `WATSUB`, `MicrobeModel`, `PlantModel`, `soluteModel`, transport, erosion, `REDIST`, balance check | `:522`; calls at `:49`, `:56`, `:63`, `:73`, `:82` |
| hourly | `hist_update`, `hist_update_hbuf`, `hist_htapes_wrapup`, optional `restFile('write')` | `:526`, `:530`, `:542`, `:548` |

## Facts a calibrator needs from this subsystem

1. **Plant parameters come from one reader.** Only `ReadPlantTraitTable` runs; `ReadPlantTraitsNC` has no caller. A name read only by the dead routine, such as `RSRA`, has no effect (`input_readers.md` §5.2).
2. **The PFT row depends on the Koppen zone.** The trait row is found by `pft_type(1:4)` plus the grid's `IETYPG` (`f90src/IOutils/PlantInfoMod.F90:1601-1604`).
3. **Traits are re-copied every year and pushed every hour.** `SetPlantTraits` runs per PFT each year (`f90src/IOutils/PlantInfoMod.F90:489`) and `SendPlantTraits` copies them into the plant kernels every hour (`f90src/APIs/PlantAPI.F90:83-85`); STARTQ-derived quantities are computed only in the first simulated year.
4. **Missing names.** A bare `ncd_getvar` of an absent variable is not caught by `check_var` and normally aborts in `check_ret`; only explicitly guarded reads (`SPOSC`, `PATM`, `XRADH`, `DRYDEPOC`, the `fAero*` fractions) tolerate absence (`input_readers.md` §5.6).
5. **History targets.** `ECO_GPP_col`, `ECO_RA_col`, `ECO_RH_col`, `ECO_ET_col` are year-to-date totals sampled instantaneously; `NPP_pft` is an hourly rate despite its `gC/m2` label (`history_and_restart.md` §3.1).
6. **Inert forcing switches.** `clm_factor_in` overlays and monthly GHG variation have no effect at this pin (`forcing.md` §3, §4.3).
7. **Management timing.** With a constant (`pft_dflag = 0`) management file, cut and harvest events start in the second simulated year (`f90src/IOutils/PlantInfoMod.F90:420-430`).

## Read-time failures and where they stop the run

| Condition | What happens | Citation |
|---|---|---|
| runfile of 4096 bytes or more | `namelist_to_buffer` does not reach end of file and calls `abort()` | `f90src/Utils/fileUtil.F90:143-150` |
| unknown key in `/ecosim/` (for example `hist_fincl4`) | namelist read error, `endrun` | `drivers/ecosim/EcoSIMAPI.F90:266-270` |
| `pft_mgmt_in='NO'` with `plant_model` on | `'NO'` opened as a file name, `check_ret` → `endrun` | `f90src/IOutils/PlantInfoMod.F90:1531`; `f90src/Utils/ncdio_pio.F90:1916` |
| `pft_file_in` path does not exist | `endrun` in `InitVegPars` | `f90src/Modelpars/PlantBGCPars.F90:196-198` |
| a name read by `ReadPlantTraitTable` is absent | `check_var` logs; `nf90_get_var` with an unset id normally fails in `check_ret` | `f90src/Utils/ncdio_pio.F90:361-406`, `:444-469` |
| PFT key (code plus Koppen zone) absent from the table | `get_pft_loc` searches without an upper bound; no message | `f90src/IOutils/PlantInfoMod.F90:1876-1880` |
| malformed planting record | `endrun` with the record text | `f90src/IOutils/PlantInfoMod.F90:181-185` |
| drought-deciduous phenology with embryophyte type outside 2 to 4 | `endrun` | `f90src/IOutils/PlantInfoMod.F90:492-500` |
| forcing year before the first daily or hourly year | `endrun` | `f90src/IOutils/ClimReadMod.F90:1048`, `:1058` |
| climate file with more than one grid | `endrun` | `f90src/IOutils/ClimReadMod.F90:736-738`, `:804-806` |
| forcing year absent from `soil_mgmt_in` | `endrun` | `f90src/IOutils/ReadManagementMod.F90:444-451` |
| `atm_ghg_in` not starting in January, or the year not fully covered | `endrun` | `f90src/IOutils/ClimReadMod.F90:951-959` |
| fire events configured with `soil_mgmt_in='NO'` | `endrun` | `f90src/Disturbances/FireMod.F90:91-92` |

Note that `ReadClimNC` itself does not check that the forcing year was found in the file (`f90src/IOutils/ClimReadMod.F90:731-734`, `:796-799`); `get_forc_step_type` guards only the lower bound.

## What changed in this subsystem since 2dea74d9

| Area | Change | Citation |
|---|---|---|
| history container | `HistDataType.F90` reduced to declarations; allocation, registration and update moved to 11 submodules | `f90src/IOutils/HistDataType.F90:672-733`; `f90src/IOutils/HistData/` |
| plant table | live reader reads `ARSRA`, `RVSR`, `RSSA`, `CYTOS`, `MRTFQ`, `STDENS` and coarse-root stoichiometry; `RSRA` read only by the dead routine | `f90src/IOutils/PlantInfoMod.F90:1734`, `:1782-1800` |
| microbial file | optional, guarded `SPOSC` | `f90src/Modelpars/NitroPars.F90:363-364` |
| namelist | `guard_floor_dying_stand`, `conserve_root_clamp`, `lcoarseroot`, `llignification` added to `/ecosim/` | `drivers/ecosim/EcoSIMAPI.F90:180-182` |
| forcing | longwave replacement, `DRYDEPOC`, `DepositionMod`, GHG validation | `forcing.md` §9 |
| grid | optional `fAero*` fractions; text log files no longer opened | `f90src/IOutils/readimod.F90:257-262`, `:399` |
| soil management | missing forcing year aborts | `f90src/IOutils/ReadManagementMod.F90:444-451` |
| restart | midnight-restart reset of `SeasonalNonstCDayAve_pft` | `f90src/IOutils/RestartMod.F90:82-87` |

## File formats

All model inputs and outputs are NetCDF opened through `ncdio_pio` (`f90src/Utils/ncdio_pio.F90:1901`). Climate data may alternatively come from the ASCII format read by `ReadClim` (`f90src/IOutils/ClimReadMod.F90:583`). The runfile is a Fortran namelist file with the groups `/ecosim/`, `/bbgcforc/`, `/ecosim_time/`, `/Microbes/`, and optionally `/FixClimForc/` and `/regression_test/` (`f90src/Utils/TestMod.F90:96`).

## Conventions shared by the readers

- **Calendar.** Arrays indexed by day are sized 366 and the year loop runs to `DazCurrYear`, 365 or 366 (`drivers/ecosim/EcoSIMAPI.F90:466`). Day-of-year values in management records are computed as `30*(month-1)+ICOR(month-1)+day+leap` (`f90src/IOutils/PlantInfoMod.F90:190-194`, `f90src/IOutils/ReadManagementMod.F90:77-83`).
- **Two years per simulated year.** Readers receive both `yearc` (model year) and `yeari` (forcing year); which one a reader keys on is listed per reader in `input_readers.md`.
- **Areas.** Model state is per grid cell (`d-2` in declaration comments); history output divides by the column footprint `AREA_3D(3,NU_col,NY,NX)` to give per square metre values.
- **Disable tokens.** `'NO'` for `soil_mgmt_in`, `clm_factor_in` and the soil-management sub-variable names; empty string for `pft_mgmt_in`, `micpar_file_in`, `pft_file_in` and the climate files.

## Links to neighbouring subsystems

- **Mass and energy balance.** `hour1` opens the hourly balance bracket with `BegCheckBalances` (`f90src/Modelforc/Hour1Mod.F90:151`); `Run_EcoSIM_one_step` closes it with `EndCheckBalances` after `DiagSoilGasPressure` (`drivers/ecosim/EcoSIMAPI.F90:122-124`). See `../diagnostics/`.
- **Water table.** `hour1` diagnoses the water-table depth per column with `DiagWaterTBLDepz` (`f90src/Modelforc/Hour1Mod.F90:178`), using the boundary conditions read by `readsiteNC`.
- **Machine-learning diagnostics.** With `lmicrobeMLdiag`, `MLDataDiag` fills the 0-30 cm and 0-60 cm summaries of `MLDataDiagType` after the microbial step (`drivers/ecosim/EcoSIMAPI.F90:66`); they are written through `update_hist_columns`.
- **Plant initialisation.** `STARTS` (soil, first year, `drivers/ecosim/EcoSIMAPI.F90:413`) and `STARTQ` (plants, first year, `:437`) consume the grid and plant tables read here; `InitControlParms` runs every year (`:407`) and re-applies `MicPar%SetPars`, including the SPOSC copy.
- **Plant and microbial kernels.** Traits read here reach the plant kernels only through the API layer (`../apis/api_layer.md`).

## Navigation

- `input_readers.md`: namelist groups and keys, runtime switches, grid reader, plant parameter readers and missing-name behaviour, microbial reader, plant and soil management, reader map for 60 calibration names.
- `forcing.md`: climate readers and units, GHGs, daily and hourly weather, radiation partitioning, inert switches.
- `history_and_restart.md`: history engine and namelist limits, submodule layout, producing chains for twelve calibration targets, restart summary.
- `../data_types/index.md`: the module-array state layer the readers fill.
- `../apis/index.md`: the copy layer between that state and the plant and microbial kernels.
