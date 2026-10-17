---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/Modelforc/{YearMod,DayMod,Hour1Mod,WthrMod,DepositionMod}.F90`, climate and GHG readers in `f90src/IOutils/{ClimReadMod,readsmod}.F90`, time loop in `drivers/ecosim/{EcoSIMAPI,ecosim}.F90`
**Last verified:** 2026-10-15
---

# Forcing Pipeline

This page follows meteorological and atmospheric forcing from file to the hourly column fields used by the physics: how the climate files are read, how daily data are disaggregated to hours, how shortwave radiation is partitioned, where atmospheric CO2 comes from, and which forcing switches are read but have no effect at this pin.

## 1. Where forcing enters the time loop

`AdvanceModelOneYear` (`drivers/ecosim/EcoSIMAPI.F90:343-571`) runs one simulated year. Order of the forcing-related calls:

| Step | Call | Citation | Cadence |
|---|---|---|---|
| 1 | `ReadPlantInfo` (plant traits and management) | `drivers/ecosim/EcoSIMAPI.F90:424` | yearly, if `plant_model` |
| 2 | `ReadClimSoilForcing` (climate, soil management, GHGs) | `drivers/ecosim/EcoSIMAPI.F90:429` | yearly |
| 3 | `DAY(I,...)` | `drivers/ecosim/EcoSIMAPI.F90:479` | daily |
| 4 | `SetAnnualAccumlators(I,...)` (acts only when `I.EQ.1`) | `drivers/ecosim/EcoSIMAPI.F90:483` | daily call |
| 5 | `PrepHourlyWeather(I,J,...)` | `drivers/ecosim/EcoSIMAPI.F90:518` | hourly, first |
| 6 | `Run_EcoSIM_one_step` → `HOUR1` first | `drivers/ecosim/EcoSIMAPI.F90:522`, `:49` | hourly, after the weather |

So the hour's weather and radiation partition are set before `hour1` runs canopy radiation (`f90src/Modelforc/Hour1Mod.F90:201`). The model clock follows the real calendar: a year has 365 or 366 days (`DazCurrYear`, used as the day loop bound at `drivers/ecosim/EcoSIMAPI.F90:466`), and the forcing readers pad day 366 with day 365 in non-leap forcing years (`f90src/IOutils/ClimReadMod.F90:777-785`, `:859-870`).

The forcing year (`frectyp%yearclm`) and the model year (`frectyp%yearcur`) differ when `forc_periods` cycles a range of forcing years (`drivers/ecosim/ecosim.F90:150-152`; see `input_readers.md` §1.5). Climate and `soil_mgmt_in` are keyed on the forcing year; `GetAtmGts` is keyed on the model year (`f90src/IOutils/readsmod.F90:246`).

## 2. Climate files: `ReadClimNC`

`ReadClimNC(yearc,yeari,L,atmf)` (`f90src/IOutils/ClimReadMod.F90:696-895`) is called from `ReadClimateForc` when the forcing year changes (`f90src/IOutils/readsmod.F90:178`). `get_forc_step_type(yeari)` (`f90src/IOutils/ClimReadMod.F90:1036-1062`) selects daily data (`IWTHR = 1`) when a daily file exists and the forcing year is before the first year of the hourly file, otherwise hourly (`IWTHR = 2`). A year not covered aborts (`:1048`, `:1058`). Only one grid cell is supported (`ngrid /= 1` aborts, `:736-738`, `:804-806`).

### 2.1 Daily branch (`clm_day_file_in`)

Reads `TMPX, TMPN, WIND, RAIN, SRAD, DWPT` for the record whose `year` equals the forcing year (`f90src/IOutils/ClimReadMod.F90:731-750`), the site scalars `Z0G, ZNOONG`, precipitation chemistry `PHRG, CN4RIG, CNORIG, CPORG, CALRG, CFERG, CCARG, CMGRG, CNARG, CKARG, CSORG, CCLRG`, and the flag `IFLGW` (`:752-766`). `DWPT` is stored in both rows of `DWPT(2,366)` (`:750`). The optional daily dry deposition of organic C `DRYDEPOC` is read if present, else zero (`:768-775`).

No unit conversion is applied on this branch. `DailyWeather` uses `WIND(I)` directly as a speed in m h-1, floored at 3600 (`f90src/Modelforc/WthrMod.F90:204`), and distributes `RAIN(I)` as `RAIN(I)/12` per hour over hours 13 to 24 (`:209-219`). The ASCII daily reader, by contrast, converts units according to the header codes (for example `WIND(I)=ABS(DAT(K))*3600.0_r8` for m s-1, `f90src/IOutils/ClimReadMod.F90:462`; `RAIN(I)=AZMAX1(DAT(K))/1.0E+03_r8` for mm, `:526`).

### 2.2 Hourly branch (`clm_hour_file_in`)

Reads `TMPH → TMP_hrly`, `WINDH`, `DWPTH`, `RAINH`, `SRADH → SWRad_hrly` as `(24,366)` arrays (`f90src/IOutils/ClimReadMod.F90:814-818`). Optional variables are guarded with `check_var`: `PATM → PBOT_hrly`, default 101.325 kPa (`:820-825`); `DRYDEPOC` (`:827-834`); `XRADH → RadLWClm`, default 0 (`:852-857`). The same site scalars and chemistry as the daily branch follow (`:836-850`). Unit conversions, applied to all 366 days (`:873-880`):

| Array | Conversion | Result units |
|---|---|---|
| `SWRad_hrly` | `*3600.e-6` | MJ m-2 h-1 (from W m-2) |
| `RadLWClm` | `*3600.e-6` | MJ m-2 h-1 (from W m-2) |
| `WINDH` | `*3600` | m h-1 (from m s-1) |
| `RAINH` | `*1.e-3` | m h-1 (from mm h-1) |

### 2.3 ASCII weather (`ReadClim`)

`ReadClim` (`f90src/IOutils/ClimReadMod.F90:583`) parses a text weather file whose header encodes the time step and the unit codes; `readdayweather` (`:341`) and `readhourweather` (`:103`) apply the unit conversions, and `interp3hourweather` (`:53`) interpolates 3-hourly records. The NetCDF path above is the one used by the shipped examples.

### 2.4 Forcing arrays and their declared units

The readers fill module arrays of `ClimForcDataType`, sized for a 366-day year. The declaration comments do not always match the units the code uses after reading; the "used as" column is what the forcing routines assume.

| Array | Declared at | Declaration comment | Used as |
|---|---|---|---|
| `TMPX(366)`, `TMPN(366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:29-30` | degC | degC (`f90src/Modelforc/DayMod.F90:159-164`) |
| `SRAD(366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:31` | MJ m-2 d-1 | MJ m-2 d-1, `RMAX = SRAD/(DayLen*0.658)` (`f90src/Modelforc/DayMod.F90:147`) |
| `RAIN(366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:32` | mm d-1 | m per day, split as `RAIN/12` into 12 afternoon hours of an m h-1 field (`f90src/Modelforc/WthrMod.F90:211`); the ASCII reader converts mm to m (`f90src/IOutils/ClimReadMod.F90:526`), the NetCDF daily reader does not |
| `WIND(366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:33` | m d-1 | m h-1, floored at 3600 (`f90src/Modelforc/WthrMod.F90:204`); the ASCII reader converts m s-1 by `*3600` (`f90src/IOutils/ClimReadMod.F90:462`), the NetCDF daily reader does not |
| `DWPT(2,366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:34` | dewpoint, degC | vapour pressure, kPa (`VPK_col` bookends, `f90src/Modelforc/DayMod.F90:165-170`) |
| `DryDepoOMC(366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:35` | gC m-2 d-1 | per-area rate scaled by column area (`f90src/Modelforc/DepositionMod.F90:49`) |
| `TMP_hrly(24,366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:37` | degC | degC |
| `SWRad_hrly(24,366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:38` | MJ m-2 h-1 | MJ m-2 h-1 after `*3600.e-6` |
| `RAINH(24,366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:39` | mm h-1 | m h-1 after `*1.e-3` |
| `WINDH(24,366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:40` | m h-1 | m h-1 after `*3600` from m s-1 |
| `DWPTH(24,366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:41` | dewpoint, degC | vapour pressure, kPa (`VPK_col = AMIN1(DWPTH,VPS)`, `f90src/Modelforc/WthrMod.F90:255`) |
| `RadLWClm(24,366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:42` | MJ m-2 h-1 | MJ m-2 h-1 after `*3600.e-6` |
| `PBOT_hrly(24,366)` | `f90src/Ecosim_datatype/ClimForcDataType.F90:43` | kPa | kPa |

## 3. Atmospheric CO2, CH4, N2O: `GetAtmGts`

`GetAtmGts(yeari,...)` (`f90src/IOutils/ClimReadMod.F90:926-996`) is called once per simulated year with the MODEL year (`f90src/IOutils/readsmod.F90:246`). It opens `atm_ghg_in` (`f90src/IOutils/ClimReadMod.F90:943`). Unless all three of `atm_co2_fix`, `atm_ch4_fix`, `atm_n2o_fix` are positive, it checks that the first time stamp is January of a year (`year + 1/12`) and that twelve months of the requested year are available, aborting otherwise (`:946-961`). It then fills `atm_co2_mon(1:12)`, `atm_ch4_mon(1:12)`, `atm_n2o_mon(1:12)`, each replaced by its `*_fix` value when that is positive (`:963-983`).

Only the January value is applied, for the whole year: `CO2EI_col = atm_co2_mon(1)`, `CO2E_col = CO2EI_col`, `CH4E_col = atm_ch4_mon(1)*1e-3`, `Z2OE_col = atm_n2o_mon(1)*1e-3` (ppb to ppm) (`:989-992`). The monthly update in `PrepHourlyWeather` is commented out (`f90src/Modelforc/WthrMod.F90:117-125`), and no other code assigns `CO2E_col` except the initial value in `readsiteNC` (`f90src/IOutils/readimod.F90:346`). Atmospheric GHGs are therefore an annual step function at this pin. `SetAtmsTracerConc` (`f90src/Modelforc/Hour1Mod.F90:275-315`) converts these mixing ratios each hour into gas mass concentrations with an ideal-gas factor `Tref/TairKClimMean_col*PBOT/101.325` (`:291-292`) and computes dissolved concentrations in rain and irrigation (`:305-310`); it does not change the mixing ratios. O2, N2, Ar, NH3 and H2 come from the namelist values set in `readsiteNC` (`f90src/IOutils/readimod.F90:315-321`, `:347`).

## 4. Daily step: `DayMod`

### 4.1 `day`

`day(I,...)` (`f90src/Modelforc/DayMod.F90:46-89`) computes the equation-of-time correction of solar noon (`:72-75`), calls `ApplyBioAerosol(I,12,NY,NX)` for every column (`:77`), then `UpdateDailyAccumulators` (`:81`), `TillageandIrrigationEvents` (`:83`) and, in prescribed-phenology mode, `PrescribePhenologyInterp` (`:85`).

`ApplyBioAerosol` (`f90src/Modelforc/DepositionMod.F90:26`) returns unless the day's `DryDepoOMC(I)` exceeds 1e-12 (`:43`). Otherwise it adds deposited organic C to the fine-litter complex, scaled by the column's `fAeroScalar_col` and split by the `fAero*` fractions read from the grid file: 97.5 % of the live-microbe part as heterotrophs via `MicrobeByLitterFall`, 2.5 % as cyanobacteria via `InoculateCyanoBacter` (`:55`, `:59`).

### 4.2 `UpdateDailyAccumulators`

`UpdateDailyAccumulators` (`f90src/Modelforc/DayMod.F90:92-216`) shifts the day length (`DayLenthPrev_col = DayLensCurr_col`, then `DayLensCurr_col = GetDayLength(ALAT_col,I)`, `:122-124`). With daily forcing it prepares the disaggregation coefficients (`:144-171`): the peak hourly radiation `RMAX = SRAD(I)/(DayLensCurr_col*0.658)` (`:147`), or `RMAX = SRAD(I)` for a phytotron (Koppen zone -2, `:152`); three temperature bookends `TAVG1, TAVG2, TAVG3` and amplitudes `AMP1..3` from the previous, current and next day's maxima and minima (`:159-164`); and the vapour-pressure equivalents `VAVG*`, `VMP*` (`:165-170`).

### 4.3 Climate-change overlays: read, accumulated, never applied

When `clm_factor_in` is not `'NO'`, `ReadClimateCorrections` (`f90src/IOutils/readsmod.F90:252`) reads monthly perturbations `DRAD, DTMPX, DTMPN, DHUM, DPREC, DIRRI, DWIND, DCN4R, DCNOR` and the mode `ICLM`. `UpdateDailyAccumulators` turns them into `TDTPX, TDTPN, TDRAD, ...` as step changes for `ICLM = 1` (`f90src/Modelforc/DayMod.F90:187-199`) or as linear annual ramps for `ICLM = 2` (`:200-211`). The routine that applies them to the hourly forcing, `CorrectClimate` (`f90src/Modelforc/WthrMod.F90:414-525`), is never called: its only call is commented out (`:112-115`). The same is true at 2dea74d9. A `clm_factor_in` scenario therefore produces an unperturbed run without any message. `CorrectClimate` also contains the only update of `rPlantThermoAdaptZone_pft` from a temperature change (`:476`), which is consequently inactive.

### 4.4 `TillageandIrrigationEvents`

`TillageandIrrigationEvents` (`f90src/Modelforc/DayMod.F90:219-308`) converts the day's `iSoilDisturbType_col` into a mixing fraction and sets `XTillCorp_col = 1 - CORP` (`:248`). With `Lirri_auto` (set when the irrigation sub-variable name starts with `auto`, `f90src/IOutils/ReadManagementMod.F90:515`), it triggers irrigation inside the configured date window when either the soil-water criterion (`iIrrig_swc`, total water below `TWP + FIRRA*(TFZ - TWP)`) or the canopy-water-potential criterion (`iIrrig_cwp`, daily minimum canopy water potential below `FIRRA`) holds, and spreads the required amount evenly over the configured hours (`f90src/Modelforc/DayMod.F90:288-293`).

## 5. Annual step: `SetAnnualAccumlators`

`SetAnnualAccumlators(I,...)` (`f90src/Modelforc/YearMod.F90:38`) is called every day after `day` but acts only when `I.EQ.1`, in either hemisphere (`:53`; the two branches of the test are identical, a placeholder for a growing-degree-day year start). On 1 January it zeroes the year-to-date counters behind the cumulative history fields, among them `QEvap_CumYr_col` (`:68`), `Eco_HR_CumYr_col` (`:83`), `Eco_GPP_CumYr_col` (`:84`), `Eco_NPP_CumYr_col` (`:85`) and `Eco_AutoR_CumYr_col` (`:86`), and rolls the per-PFT cumulative fluxes. Restart runs call it again at hour 1 after reading the checkpoint (`drivers/ecosim/EcoSIMAPI.F90:497-501`).

## 6. Hourly weather: `PrepHourlyWeather`

`PrepHourlyWeather(I,J,...)` (`f90src/Modelforc/WthrMod.F90:51-129`) sets the fractional day `DOY = I-1+J/24` (`:74`) and branches on `IWTHR`: `DailyWeather` for daily forcing (`:92`), the ATS-coupled radiation path for `IWTHR = -999` (`:96-98`), `HourlyWeather` otherwise (`:100`). It then applies open-top-chamber and infrared warming when `check_warming_dates` is true (`:103-107`), partitions radiation in `CalcRadiation` (`:109`) and accumulates climate summaries in `SummaryClimateForc` (`:127`). Module constants: solar constant `SolConst = 4.896` MJ m-2 h-1, visible fractions `CDIR = 0.42`, `CDIF = 0.58`, PAR conversion `PDIR = PDIF = 1269.4`, snow threshold `TSNOW = -0.25` degC (`:41-46`).

### 6.1 `DailyWeather`

`DailyWeather` (`f90src/Modelforc/WthrMod.F90:132-225`): shortwave `RADN_col = AZMAX1(RMAX*SIN((J-(SolarNoonHour-DayLen/2))*PICON/DayLen))` (`:154-155`), or `RMAX/24` for a phytotron (`:162`); air temperature and vapour pressure from piecewise sinusoids around solar noon using the `TAVG*`, `AMP*`, `VAVG*`, `VMP*` coefficients (`:167-196`); vapour pressure capped at saturation corrected for altitude (`:197-198`); surface pressure from altitude (`:199`); wind `AMAX1(3600, WIND(I))` (`:204`); precipitation `RAIN(I)/12` per hour for hours 13 to 24, as rain when `TCA_col > TSNOW` and as snow otherwise, none for hours 1 to 12 (`:209-222`).

### 6.2 `HourlyWeather`

`HourlyWeather` (`f90src/Modelforc/WthrMod.F90:228-271`) copies the hour: `RADN_col = SWRad_hrly(J,I)`, `TCA_col = TMP_hrly(J,I)` (`:249-250`); `VPK_col = AMIN1(DWPTH(J,I), VPS)` with `VPS = vapsat0(TairK)*EXP(-ALTI/7272)` (`:254-255`); `WindSpeedAtm_col = AMAX1(3600, WINDH(J,I))` (`:256`); `PBOT_col = PBOT_hrly(J,I)` (`:257`); the whole hour's `RAINH` as rain or snow by the `TSNOW` test (`:259-265`). It resets `EMS_Modify_Scalar_col` and `srad_scalar_col` to 1 (`:266-267`).

### 6.3 `CalcRadiation`

`CalcRadiation` (`f90src/Modelforc/WthrMod.F90:274-411`), per column and hour:

1. Sine of solar elevation `AZMAX1(AZI + DEC*COS(PICON12*(SolarNoonHour - (J-0.5))))` with `AZI = sin(lat)sin(decl)` and `DEC = cos(lat)cos(decl)` (`:305-306`, `:313`); under `fixClime` the sun is held at local noon (`:308-311`).
2. Top-of-atmosphere bound `RADX = SolConst*AZMAX1(SineSunInclinationAngle_col)` (`:321`).
3. Diffuse `RADZ = AMIN1(RADN, 0.5*(RADX - RADN))` (`:329`); direct beam `RadSWDirect_col = safe_adb(RADN - RADZ, sine)`, capped at 4.167 and scaled by `srad_scalar_col` (`:330-331`); diffuse per unit sky `RadSWDiffus_col = RADZ/TotSineSkyAngles_grd*srad_scalar_col` (`:332`); PAR `RadDirectPAR_col = RadSWDirect_col*CDIR*PDIR`, `RadPARDiffus_col = RadSWDiffus_col*CDIF*PDIF` (`:333-334`).
4. Cloudiness `CLD = AMIN1(1, AMAX1(0.2, 2.33 - 3.33*RADN/RADX))` (`:343`) and sky emissivity `EMM = 0.625*AMAX1(1, (1e3*VPK/TairK)**0.131)*(1 + 0.242*CLD**0.583)` (`:347-348`).
5. Downwelling longwave: if the forcing supplies `RadLWClm(J,I) > 0`, `SkyLonwRad_col = RadLWClm(J,I)`; otherwise `SkyLonwRad_col = EMM*stefboltz_const*TairK**4` (`:369-375`). The observed value replaces the estimate; at 2dea74d9 it was added to it.
6. Surface irrigation `PRECII_col = RRIG(J,I,NY,NX)`; subsurface irrigation `PRECUI_col = 0` (`:403-404`).

### 6.4 Warming experiments

`warming_exp` (namelist) is parsed by `config_soil_warming` (`f90src/Disturbances/EcosysWarmingMod.F90:198-288`) when its length exceeds 10 characters (`drivers/ecosim/EcoSIMAPI.F90:315`). Each hour, `check_warming_dates` (`f90src/Disturbances/EcosysWarmingMod.F90:130-168`) decides whether `apply_OTC_warming` (`:504-536`) and `apply_IR_warming` (`:576-604`) run, before radiation is partitioned (`f90src/Modelforc/WthrMod.F90:103-107`). A reference soil-temperature series is loaded once for any warmed year by `read_soil_warming_Tref` (`f90src/IOutils/ClimReadMod.F90:1064-1117`; called from `drivers/ecosim/EcoSIMAPI.F90:455`).

### 6.5 `SummaryClimateForc`

`SummaryClimateForc` (`f90src/Modelforc/WthrMod.F90:528-575`) stores the hour's rain, snow and irrigation in the column precipitation fields and updates running climate summaries used by plant acclimation.

## 7. Hourly state reset: `hour1`

`hour1(I,J,...)` (`f90src/Modelforc/Hour1Mod.F90:85-250`) runs first inside `Run_EcoSIM_one_step`. Sequence: `ResetLndscapeAccumlators` (`:106`), `SetAtmsTracerConc` (`:109`), `ResetFluxArrays` (`:114`), `ResetSaltModelArrays` when the salt model is on (`:120`), `UpdateLiterPropertz` (`:142`), `SetLiterSoilPropAftDisturb` (`:147`), optional `SummarizeTracerMass` (`:149`), `BegCheckBalances` (`:151`), `SetSurfaceProp4SedErosion` (`:154`); then per column `SetHourlyDiagnostics` (`:163`), `DiagWaterTBLDepz` (`:178`), `GetSoilHydraulicVars` (`:188`), optional `ForceGasAquaEquil` (`:199`) and canopy radiation `PlantCanopyRadsModel` (`:201`); `CanopyInterceptPrecip` (`:238`); and `ApplyFertilizerAtNoon` (`:247`). `InitHour1` (`:73`) sets the litter water-retention capacities `THETRX = (/4.0E-06, 8.0E-06, 8.0E-06/)` m3 gC-1 (`:80`).

## 8. Forcing switches at a glance

| Switch | Where set | Effect at cb243228 |
|---|---|---|
| `IWTHR` | `get_forc_step_type` (`f90src/IOutils/ClimReadMod.F90:1036`) | 1 daily, 2 hourly, -999 ATS coupling |
| `fixClime` | `/ecosim/`; declared `f90src/Modelconfig/EcoSIMCtrlMod.F90:114` | constant climate from `/FixClimForc/` (`f90src/IOutils/readsmod.F90:169-171`); sun held at noon (`f90src/Modelforc/WthrMod.F90:308-311`) |
| `atm_co2_fix`, `atm_ch4_fix`, `atm_n2o_fix` | `/ecosim/`, default -100 (`drivers/ecosim/EcoSIMAPI.F90:258-260`) | positive value pins the annual value (`f90src/IOutils/ClimReadMod.F90:963-983`) |
| `clm_factor_in`, `ICLM` | `/ecosim/`; `ReadClimateCorrections` | read and accumulated, NOT applied (`CorrectClimate` call commented, `f90src/Modelforc/WthrMod.F90:114`) |
| `warming_exp` | `/ecosim/` (`drivers/ecosim/EcoSIMAPI.F90:315`) | OTC and IR warming windows (`f90src/Modelforc/WthrMod.F90:103-107`) |
| `Lirri_auto` | `irrigf(1:4)=='auto'` (`f90src/IOutils/ReadManagementMod.F90:515`) | automatic irrigation (`f90src/Modelforc/DayMod.F90:269-293`) |
| `XRADH` present | hourly climate file | replaces the emissivity-based longwave (`f90src/Modelforc/WthrMod.F90:369-375`) |
| `DRYDEPOC` present | climate file | daily bioaerosol C deposition (`f90src/Modelforc/DepositionMod.F90:43-59`) |

## 9. Forcing behaviour that changed between 2dea74d9 and cb243228

- Observed longwave `XRADH` now replaces the emissivity estimate instead of being added to it (`f90src/Modelforc/WthrMod.F90:369-375`).
- New optional daily organic-C dry deposition `DRYDEPOC` in both climate files (`f90src/IOutils/ClimReadMod.F90:768-775`, `:827-834`), applied by the new `DepositionMod::ApplyBioAerosol` (`f90src/Modelforc/DepositionMod.F90:26`) with partition fractions from the grid file (`f90src/IOutils/readimod.F90:257-262`).
- `GetAtmGts` validates the January time stamp and year coverage of `atm_ghg_in` and aborts on a gap (`f90src/IOutils/ClimReadMod.F90:946-961`).
- `ReadManagementFiles` aborts when the forcing year is missing from `soil_mgmt_in` (`f90src/IOutils/ReadManagementMod.F90:444-451`).
- Unchanged and still inert at both pins: the `CorrectClimate` call (`f90src/Modelforc/WthrMod.F90:114`) and the monthly GHG update (`:117-125`).
