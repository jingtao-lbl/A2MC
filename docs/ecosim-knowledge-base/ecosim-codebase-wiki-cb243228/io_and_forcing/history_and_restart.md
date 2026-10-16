---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/IOutils/{HistFileMod,HistDataType,RestartMod,restUtilMod,bhistMod,ForcWriterMod}.F90`, `f90src/IOutils/HistData/*.F90`, history and restart calls in `drivers/ecosim/EcoSIMAPI.F90`
**Last verified:** 2026-10-15
---

# History Tapes and Restart Files

EcoSIM writes four kinds of output:

1. **History tapes** (`HistFileMod` + `HistDataType` and its `HistData/` submodules): up to six NetCDF time series with per-field averaging. Every calibration target used by A2MC EcoSIM cases is a field on these tapes (section 3).
2. **Restart files** (`RestartMod` + `restUtilMod`): full state checkpoints, plus history-buffer checkpoints written alongside.
3. **Auxiliary multi-clock writer** (`bhistMod`): used by the box and aquachem test drivers, not by the main ecosim driver.
4. **Batch soil-BGC dump** (`ForcWriterMod`): a one-shot initial-condition file for a standalone soil-BGC model.

## 1. History tape engine (`HistFileMod.F90`)

### 1.1 Limits, types and defaults

| Item | Value | Citation |
|---|---|---|
| maximum tapes | `max_tapes = 6` | `f90src/IOutils/HistFileMod.F90:24` |
| maximum fields in the master list | `max_flds = 2500` | `f90src/IOutils/HistFileMod.F90:25` |
| default samples per file | `hist_mfilt = (/ 1, 30, 30, 30, 30, 30 /)` | `f90src/IOutils/HistFileMod.F90:48` |
| default write frequency | `hist_nhtfrq = (/ 0, -24, -24, -24, -24, -24 /)`: 0 monthly, `-N` every N hours, `+N` every N steps | `f90src/IOutils/HistFileMod.F90:51` |
| default-field suppression | `hist_empty_htapes = .false.` | `f90src/IOutils/HistFileMod.F90:42` |
| output precision code | `hist_ndens = 2` | `f90src/IOutils/HistFileMod.F90:45` |
| inclusion and exclusion lists | `hist_fincl1..6`, `hist_fexcl1..6` | `f90src/IOutils/HistFileMod.F90:65-89` |

### 1.2 What the runfile can actually configure

Only six history controls are members of the `/ecosim/` namelist group: `hist_nhtfrq, hist_mfilt, hist_fincl1, hist_fincl2, hist_fincl3, hist_yrclose` (`drivers/ecosim/EcoSIMAPI.F90:180`). The other module variables in the table above (`hist_fincl4-6`, every `hist_fexcl*`, `hist_empty_htapes`, `hist_ndens`, `hist_avgflag_pertape`, `hist_type1d_pertape`) keep their compiled defaults. Writing one of them into the runfile makes the namelist read fail and the driver stops in `endrun` (`drivers/ecosim/EcoSIMAPI.F90:266-270`). In practice a run has at most three configurable tapes, and tape 1 also receives every field registered without `default='inactive'` because `hist_empty_htapes` cannot be switched on (`f90src/IOutils/HistFileMod.F90:861-874`, in `htapes_fieldlist`).

### 1.3 Field registration

`hist_addfld1d` (`f90src/IOutils/HistFileMod.F90:353`) and `hist_addfld2d` (`:534`) store a pointer to the live buffer and add a master-list entry through `masterlist_addfld` (`:425`). The optional argument `default='inactive'` keeps a field off tape 1 unless it is named in an inclusion list (`:415` for 1-D, `:621` for 2-D). The registration calls themselves are in the `register_hist_*` submodule procedures (section 2): 225 call lines in `HistRegisterColumn.F90`, 180 in `HistRegisterPlant.F90`, 138 in `HistRegisterSoilBGC.F90`, 110 in `HistRegisterSoilPhysRoot.F90`. An inclusion-list entry may carry an averaging suffix `NAME:F`, parsed by `getname` (`:1012`) and `getflag` (`:1042`).

### 1.4 Averaging flags

| Flag | Meaning | Where applied |
|---|---|---|
| `A` | time average over the write interval | `hist_update_hbuf_field_1d`, `f90src/IOutils/HistFileMod.F90:1358` |
| `I` | instantaneous value at the last step of the interval | `f90src/IOutils/HistFileMod.F90:1341` |
| `X`, `M` | maximum, minimum over the interval | flag table in `f90src/IOutils/HistFileMod.F90:1222-1224` |
| `P` | average over positive values (per-tape override only) | `f90src/IOutils/HistFileMod.F90:1218` |

A field registered with flag `I` whose source is a year-to-date cumulative counter therefore reports, at each write, the total since 1 January up to that step (section 3.1).

### 1.5 Per-step sequence in the driver

Inside the hourly loop of `AdvanceModelOneYear`, after the physics step: `call hist_ecosim%hist_update(yearIJ%I,yearIJ%J,bounds)` copies model state into the history buffers (`drivers/ecosim/EcoSIMAPI.F90:526`); `call hist_update_hbuf(bounds)` accumulates them per tape and flag (`:530`; routine at `f90src/IOutils/HistFileMod.F90:1235`); the clock advances (`drivers/ecosim/EcoSIMAPI.F90:534`); `call hist_htapes_wrapup(rstwr, nlend, bounds, lnyr)` normalises, writes and rolls files (`:542`; routine at `f90src/IOutils/HistFileMod.F90:1660`); a restart is written when `rstwr` is true (`drivers/ecosim/EcoSIMAPI.F90:545-550`).

### 1.6 File names

`set_hist_filename` (`f90src/IOutils/HistFileMod.F90:2147-2186`) builds `./<case_name>.ecosim<inst_suffix>.h<N>.<date>.nc` (`:2183`), with a month-resolution date for monthly tapes. History restart files per tape are named at `:2329` (`.rh<N>.`).

### 1.7 Dimensions on every tape

`htape_create` (`f90src/IOutils/HistFileMod.F90:182`) defines these dimensions (`:242-262`):

| Dimension | Size | Line |
|---|---|---|
| `gridcell`, `topounit`, `column`, `pft` | counts from the grid bounds | `:242-245` |
| `node` | `MaxNodesPerBranch` | `:248` |
| `levsoi`, `levsno`, `levcan` | `JZ`, `JS`, `NumCanopyLayers` | `:249-251` |
| `npfts`, `nbranches`, `ngrstages` | `JP`, `MaxNumBranches`, `NumGrowthStages` | `:252-254` |
| `elements`, `rootaxs` | `NumPlantChemElms`, `MaxNumRootAxes` | `:255-256` |
| `nkinecomp`, `nomcomplx`, `pmorphunits` | `jsken`, `jcplx`, `NumOfPlantMorphUnits` | `:257-259` |
| `hist_interval`, `time` (unlimited) | 2, unlimited; history tapes only, not history restarts | `:261-262` |

PFT fields (`*_pft`) are written along `pft`, so a column with several PFTs produces one value per PFT slot; column fields (`*_col`) along `column`.

## 2. History data container: `HistDataType.F90` and `HistData/`

`HistDataType.F90` (752 lines) declares the type `histdata_type` (`f90src/IOutils/HistDataType.F90:9-668`), with one pointer component per tape field: `h1D_*_col` (column), `h1D_*_ptc` (PFT), `h2D_*` (profiles), type-bound `Init => init_hist_data`, `hist_update` and the private `ZeroPlantHistVars` (`:664-668`). The singleton is `hist_ecosim` (`:670`). Every implementation lives in Fortran submodules declared by the interface block (`:672-733`):

| Submodule file | Lines | Module procedure | Role |
|---|---|---|---|
| `HistData/HistAllocateColumn.F90` | 239 | `allocate_hist_columns` (`:8`) | allocate column buffers, initialised to `spval` |
| `HistData/HistAllocatePlant.F90` | 198 | `allocate_hist_plants` (`:6`) | allocate PFT buffers |
| `HistData/HistAllocateProfile.F90` | 277 | `allocate_hist_profiles` (`:9`) | allocate 2-D profile buffers |
| `HistData/HistRegisterColumn.F90` | 973 | `register_hist_columns` (`:7`) | register column fields |
| `HistData/HistRegisterPlant.F90` | 811 | `register_hist_plants` (`:6`) | register PFT fields |
| `HistData/HistRegisterSoilBGC.F90` | 635 | `register_hist_soil_bgc` (`:9`) | register soil BGC profiles |
| `HistData/HistRegisterSoilPhysRoot.F90` | 469 | `register_hist_soil_phys_root` (`:8`) | register soil physics and root profiles |
| `HistData/HistUpdate.F90` | 250 | `hist_update` (`:8`), `ZeroPlantHistVars` (`:26`) | per-step dispatcher; zeroing for dead PFTs |
| `HistData/HistUpdateColumn.F90` | 396 | `update_hist_columns` (`:65`) | fill column buffers |
| `HistData/HistUpdatePlant.F90` | 470 | `update_hist_plants` (`:59`) | fill PFT buffers |
| `HistData/HistUpdateSoil.F90` | 264 | `update_hist_soil` (`:37`) | fill profile buffers |

`init_hist_data` (`f90src/IOutils/HistDataType.F90:737-750`) runs the three allocation procedures and then the four registration procedures; registration order fixes field indices. `hist_update` loops over columns and calls `update_hist_columns`, `update_hist_soil`, `update_hist_plants` in that order (`f90src/IOutils/HistData/HistUpdate.F90:13-22`).

Conventions inside the update procedures: extensive quantities are divided by the column footprint `AREA_3D(3,NU_col(NY,NX),NY,NX)`, converting the model's per-cell `d-2` units to per square metre; constants `secs1hour = 3600`, `MJ2W = 1.e6/secs1hour`, `m2mm = 1000`, `million = 1.e6` are local parameters (`f90src/IOutils/HistData/HistUpdateColumn.F90:68-71`). In `update_hist_plants`, a PFT with `PlantPopuLive_pft <= 0` has most of its buffers zeroed by `ZeroPlantHistVars` and the rest of its loop body skipped (`f90src/IOutils/HistData/HistUpdatePlant.F90:121-124`); fields assigned before that test (for example `NPP_pft`, `:94`) are still written.

## 3. Calibration targets on the tape: producing chains

The code tools at this pin cannot name a routine inside a Fortran submodule `module procedure` body; the procedure names below were read from the files.

| Tape field | Registered (file:line; units; flag; default) | Filled at (procedure, file:line) | Model variable copied | One hop back: where that variable is computed |
|---|---|---|---|---|
| `ECO_GPP_col` | `f90src/IOutils/HistData/HistRegisterColumn.F90:507-509`; `gC/m2`; `I` | `update_hist_columns`, `f90src/IOutils/HistData/HistUpdateColumn.F90:202`: `h1D_Eco_GPP_CumYr_col = Eco_GPP_CumYr_col/AREA_3D(3,NU)` | `Eco_GPP_CumYr_col`, `[g d-2]` (`f90src/Ecosim_datatype/EcosimBGCFluxType.F90:18`) | `ReceivePlantState`: `Eco_GPP_CumYr_col = Eco_GPP_CumYr_col + AZERO(plt_bgcr%GrossCO2Fix_pft(NZ))` every hour (`f90src/APIs/PlantStateTransferMod.F90:58`); zeroed on day 1 by `SetAnnualAccumlators` (`f90src/Modelforc/YearMod.F90:84`) |
| `ECO_RA_col` | `HistRegisterColumn.F90:511-513`; `gC/m2`; `I` | `update_hist_columns`, `HistUpdateColumn.F90:203` | `Eco_AutoR_CumYr_col`, `[gC d-2]` (`EcosimBGCFluxType.F90:19`) | `ReceivePlantColumns`: `= AZERO(plt_bgcr%Eco_AutoR_CumYr_col)` (`f90src/APIs/PlantColumnTransferMod.F90:64`); the plant kernels decrement the copy, e.g. `Eco_AutoR_CumYr_col - Rauto_brch` in `ComputRAutoAfEmergence` (`f90src/Plant_bgc/PlantBranchMod.F90:3295`); zeroed yearly (`YearMod.F90:86`) |
| `ECO_RH_col` | `HistRegisterColumn.F90:519-521`; `gC/m2`; `I`; long name "(<0 into atmosphere)" | `update_hist_columns`, `HistUpdateColumn.F90:205` | `Eco_HR_CumYr_col`, `[gC d-2]` (`EcosimBGCFluxType.F90:21`) | `UpdateOutputVars`: `Eco_HR_CumYr_col + ECO_HR_CO2_col + ECO_HR_CH4_col` (`f90src/Balances/RedistMod.F90:234`), with `ECO_HR_CO2_col = sum(ECO_HR_CO2_vr(0:JZ))` (`:232`); zeroed yearly (`YearMod.F90:83`) |
| `ECO_ET_col` | `HistRegisterColumn.F90:559-561`; `mm H2O/m2`; `I` | `update_hist_columns`, `HistUpdateColumn.F90:213`: `m2mm*QEvap_CumYr_col/AREA_3D(3,NU)` | `QEvap_CumYr_col`, `[m3 d-2]` (`f90src/Ecosim_datatype/SoilWaterDataType.F90:87`) | `HandleSurfaceBoundary`: `QEvap_CumYr_col = QEvap_CumYr_col - WO` (`f90src/Balances/RedistMod.F90:410`), `WO = VapXAir2GSurf_col + QVegET_col` (`:408`); positive into the atmosphere; zeroed yearly (`YearMod.F90:68`) |
| `CO2_SEMIS_FLX_col` | `HistRegisterColumn.F90:690-693`; `umol C/m2/s`; `A`; "(< 0 into atmosphere), excluding wet deposition" | `update_hist_columns`, `HistUpdateColumn.F90:242`: `SurfGasEmiss_all_flx_col(idg_CO2)/AREA*GramPerHr2umolPerSec(idg_CO2)` | `SurfGasEmiss_all_flx_col`, `[g d-2 h-1]` (`f90src/Ecosim_datatype/SoilBGCDataType.F90:49`) | `UpdateOutputVars`: set from `SurfGasEmiss_flx_col` (`f90src/Balances/RedistMod.F90:173`) then adds root disturbance loss and air-to-root flux (`:211-212`) |
| `CAN_GPP_pft` | `f90src/IOutils/HistData/HistRegisterPlant.F90:32-34`; `gC/m2/hr`; `A`; inactive | `update_hist_plants`, `f90src/IOutils/HistData/HistUpdatePlant.F90:155` | `GrossCO2Fix_pft`, `[g d-2 h-1]` (`f90src/Ecosim_datatype/PlantDataRateType.F90:33`) | `ReceivePlantState` copy (`f90src/APIs/PlantStateTransferMod.F90:123`) of the kernel value accumulated over branches in `ComputRAutoAfEmergence`, `GrossCO2Fix_pft(NZ) + CO2F` (`f90src/Plant_bgc/PlantBranchMod.F90:3289`), reset each hour in `ZeroGrosub` (`f90src/Plant_bgc/PlantBalMod.F90:502`, called from `EnterPlantBalance` `:709`) |
| `NPP_pft` | `HistRegisterPlant.F90:412-414`; `gC/m2`; `A` | `update_hist_plants`, `HistUpdatePlant.F90:94` (before the dead-PFT test) | `NetPrimProduct_pft`, declared "Hourly net primary productivity, [g d-2 h-1]" (`PlantDataRateType.F90:42`) | `Live2DeadTransformation`: `NetPrimProduct_pft = GrossCO2Fix_pft + GrossResp_pft` (`f90src/Plant_bgc/GrosubsMod.F90:253`), `GrossResp_pft = RootAutoCO2_pft + CanopyGrosRCO2_pft` (`f90src/Plant_bgc/PlantBalMod.F90:99`, negative = respired); copied back at `PlantStateTransferMod.F90:243` |
| `SHOOT_C_pft` | `HistRegisterPlant.F90:210-212`; `gC/m2`; `A` | `update_hist_plants`, `HistUpdatePlant.F90:191` | `ShootElms_pft(ielmc,...)`, `[g d-2]` (`f90src/Ecosim_datatype/CanopyDataType.F90:134`) | `SumCanopyBiome`: `AZMAX1(sum(ShootElms_brch(NE,1:NumOfBranches_pft)))` (`f90src/Plant_bgc/PlantBalMod.F90:290`); copied back at `PlantStateTransferMod.F90:84` |
| `Plant_C_pft` | `HistRegisterPlant.F90:224-226`; `gC/m2`; `A` | `update_hist_plants`, `HistUpdatePlant.F90:192-193`: `(ShootElms_pft(ielmc) + RootElms_pft(ielmc))/AREA` | shoot plus root element pools | as `SHOOT_C_pft` and `Root_C_pft` |
| `LEAF_C_pft` | `HistRegisterPlant.F90:236-238`; `gC/m2`; `A`; inactive | `update_hist_plants`, `HistUpdatePlant.F90:196` | `LeafStrutElms_pft(ielmc,...)`, `[g d-2]` (`CanopyDataType.F90:135`) | `SumCanopyBiome`: `AZMAX1(sum(LeafStrutElms_brch(NE,1:NumOfBranches_pft)))` (`PlantBalMod.F90:291`); copied back at `PlantStateTransferMod.F90:85` |
| `Root_C_pft` | `HistRegisterPlant.F90:260-262`; `gC/m2`; `A`; "excluding nodule" | `update_hist_plants`, `HistUpdatePlant.F90:203` | `RootElms_pft(ielmc,...)`, `[g d-2]` (`f90src/Ecosim_datatype/RootDataType.F90:118`) | `SumRootBiome`: `RootElms_pft(NE,NZ) = massr1st1(NE)+massr2nd1(NE)+massnonst1(NE)` (`PlantBalMod.F90:586`); copied back at `PlantStateTransferMod.F90:67` |
| `LAI_xstk_pft` | `HistRegisterPlant.F90:360-362`; `m2/m2`; `A`; inactive; "whole plant leaf area, exclude stalk" | `update_hist_plants`, `HistUpdatePlant.F90:214` | `CanopyLeafArea_pft`, `[m2 d-2]` (`f90src/Ecosim_datatype/PlantTraitDataType.F90:24`) | `AccumulateStates`: `CanopyLeafArea_pft(NZ) + LeafAreaLive_brch(NB,NZ)` (`f90src/Plant_bgc/GrosubsMod.F90:653`); copied back at `PlantStateTransferMod.F90:94` |

### 3.1 Reading these fields correctly

- **Cumulative `I` fields.** `ECO_GPP_col`, `ECO_RA_col`, `ECO_RH_col` and `ECO_ET_col` are year-to-date totals sampled instantaneously. With a daily tape (`hist_nhtfrq = -24`), each sample is the total from 1 January through the last hour of that day. A daily flux is the difference of consecutive samples, except on 1 January when the counters restart at zero (`f90src/Modelforc/YearMod.F90:53`, gated `I.EQ.1`; called every day after `DAY`, `drivers/ecosim/EcoSIMAPI.F90:479-483`).
- **Sign conventions.** `ECO_RA_col` accumulates respiration as negative (`PlantBranchMod.F90:3295` subtracts `Rauto_brch`). `ECO_RH_col` and `CO2_SEMIS_FLX_col` carry "< 0 into atmosphere" in their long names. `ECO_ET_col` is positive into the atmosphere.
- **`NPP_pft` units.** The tape label is `gC/m2`, but the source is an hourly rate in `g d-2 h-1`, reset each hour by `ZeroGrosub` before the plant step. With flag `A` the tape value is the mean hourly NPP over the interval, in gC m-2 h-1. `CAN_GPP_pft` (`gC/m2/hr`) has the same time basis.
- **Inactive by default.** `CAN_GPP_pft`, `LEAF_C_pft` and `LAI_xstk_pft` are registered with `default='inactive'`, so they appear only when named in `hist_fincl1`, `hist_fincl2` or `hist_fincl3`.
- **Dead PFTs.** When `PlantPopuLive_pft <= 0`, `CAN_GPP_pft`, `SHOOT_C_pft`, `Plant_C_pft`, `LEAF_C_pft`, `Root_C_pft` and `LAI_xstk_pft` are set to zero by `ZeroPlantHistVars` (`f90src/IOutils/HistData/HistUpdate.F90:109`, `:142`, `:143`, `:146`, `:152`, `:163`); `NPP_pft` is still copied from the model.
- **Biomass fields are pools, not fluxes.** `SHOOT_C_pft`, `LEAF_C_pft`, `Root_C_pft` and `Plant_C_pft` are interval means (flag `A`) of carbon stocks. Per branch, `SumPlantBranchBiome` sets `ShootElms_brch = LeafStrut + PetolShethStrut + StalkStrut + StalkRsrv + HuskStrut + EarStrut + GrainStrut + CanopyNonst` (`f90src/Plant_bgc/PlantBalMod.F90:377-380`), plus, for C4 plants, the node pools `CPOOL3_node`, `CPOOL4_node`, `CMassCO2BundleSheath_node` and `CMassHCO3BundleSheath_node` (`:384-391`); `SHOOT_C_pft` is that sum over branches. `LEAF_C_pft` is the leaf structural pool only. Nodules are not in either.

### 3.2 Neighbouring fields for checking a target

These fields share the producing variables above and help decide which part of a target is off.

| Tape field | Registered (file:line; units; flag) | Filled at (file:line) | Content |
|---|---|---|---|
| `ECO_NPP_col` | `f90src/IOutils/HistData/HistRegisterColumn.F90:515-516`; `gC/m2`; `I` | `f90src/IOutils/HistData/HistUpdateColumn.F90:204` | year-to-date ecosystem NPP, `Eco_NPP_CumYr_col = Eco_GPP_CumYr_col + Eco_AutoR_CumYr_col` (`f90src/Balances/RedistMod.F90:226`, `UpdateOutputVars`) |
| `NBP_col` | `HistRegisterColumn.F90:494-495`; `gC/m2`; `I` | `HistUpdateColumn.F90:197` | year-to-date net biome production `Eco_NBP_CumYr_col` |
| `ECO_HR_CO2_col` | `HistRegisterColumn.F90:524-525`; `gC/m2/hr`; `A` | `HistUpdateColumn.F90:206` | hourly heterotrophic CO2, the CO2 part of the `ECO_RH_col` increment |
| `ECO_NEE_CO2_col` | `HistRegisterColumn.F90:700-701`; `umol C/m2/s`; `A` | `HistUpdateColumn.F90:244` | `Eco_NEE_col` converted with `GramPerHr2umolPerSec(idg_CO2)` |
| `ECO_LE_col` | `HistRegisterColumn.F90:665-666`; `W/m2`; `A` | `HistUpdateColumn.F90:238` | ecosystem latent heat `Eco_Heat_Latent_col*MJ2W/AREA` |
| `ECO_LAI_col` | `HistRegisterColumn.F90:499-500`; `m2/m2`; `A` | `HistUpdateColumn.F90:200` | column leaf area `CanopyLeafArea_col/AREA` |
| `CAN_cumGPP_pft` | `f90src/IOutils/HistData/HistRegisterPlant.F90:36-37`; `gC/m2`; `I` | `f90src/IOutils/HistData/HistUpdatePlant.F90:83` | year-to-date PFT GPP `GrossCO2Fix_CumYr_pft` |
| `CAN_RA_pft` | `HistRegisterPlant.F90:50-51`; `gC/m2/hr`; `A` | `HistUpdatePlant.F90:156` | canopy autotrophic respiration `CanopyGrosRCO2_pft` |
| `AUTO_RESP_pft` | `HistRegisterPlant.F90:376-377`; `gC/m2/hr`; `A` | `HistUpdatePlant.F90:215` | whole-plant `GrossResp_pft`, the respiration term of `NPP_pft` |
| `dCAN_GPP_CLIM_pft`, `dCAN_GPP_eLIM_pft` | `HistRegisterPlant.F90:40-41`, `:45-46`; `gC/m2/hr`; `A` | `HistUpdatePlant.F90:135-136` | GPP shortfall against the CO2-limited and light-limited rates, written only when both rates are defined (`:134`) |
| `STALK_C_pft`, `RESERVE_C_pft` | `HistRegisterPlant.F90:244-245`, `:248-249`; `gC/m2`; `A` | `HistUpdatePlant.F90:198-199` | stalk structural and stalk reserve C, two of the eight terms of `SHOOT_C_pft` |

## 4. Restart files (`RestartMod.F90`, 10543 lines)

`RestartMod` holds the checkpoint read and write logic for every state category; its size comes from one `restartvar` call per checkpointed array. Its role in summary:

- **Entry.** `restFile(flag)` (`f90src/IOutils/RestartMod.F90:70-94`) is the only public driver routine. `'read'` locates the file through the pointer file (`restFile_getfile`, `:9830`) and calls `restFile_read` (`:10039`); after a midnight restart it zeroes `SeasonalNonstCDayAve_pft` because `DAY` reset it before the checkpoint was read (`:82-87`). `'write'` forms the date stamp, names the file with `restFile_filename` (`:10150-10170`, `./<case>.ecosim<suffix>.r.<date>.nc`) and calls `restFile_write` (`:10173`).
- **Write order.** `restFile_write` defines and then writes, in order, the time manager (`timemgr_restart_io`, `:10248`), the history buffers (`hist_restart_ncd`, `f90src/IOutils/HistFileMod.F90:2189`) and the model state (`restartnc`), see `f90src/IOutils/RestartMod.F90:10206-10224`.
- **State.** `restartnc` (`:4968-4977`) calls `restartnc_plant` (`:97-4964`) and `restartnc_soil` (`:4980-9826`).
- **Variable helper.** `restartvar` is an overloaded interface over types and ranks 0 to 5 (`f90src/IOutils/restUtilMod.F90:28-40`), with interpolation flags `iflag_interp = 1`, `iflag_copy = 2`, `iflag_skip = 3` (`:42-44`) and `cpcol`, `cppft` copy interfaces (`:18-26`).
- **Cadence.** `rest_opt` and `rest_frq` (`f90src/IOutils/RestartMod.F90:57-58`) are set from `/ecosim_time/` (`f90src/Utils/ecosim_time_mod.F90:240-241`); the driver writes when `etimer%its_time_to_write_restart` is true (`drivers/ecosim/EcoSIMAPI.F90:537`, `:545-550`).
- **Read at start.** On a restart or branch run, the first matching hour reads the checkpoint and re-runs `SetAnnualAccumlators` at hour 1 (`drivers/ecosim/EcoSIMAPI.F90:491-506`).
- **Not checkpointed.** Parameter-derived quantities computed in STARTQ, such as `RootSingleVesselRstAxial_pft` (`f90src/Ecosim_mods/StartqMod.F90:580`), do not appear in `RestartMod.F90`; they come from the STARTQ call of the run's first year.

## 5. Auxiliary writers

**`bhistMod.F90`** defines `histf_type` (`f90src/IOutils/bhistMod.F90:27-62`) with `init` (`:117`), `hist_wrap` (`:290`) and `histrst` (`:66`). Each variable is assigned a clock (`hour`, `day`, `week`, `month`, `year`). It is used by `drivers/aquachem/aquachem.F90:53` and the batch soil-BGC driver, not by `drivers/ecosim/`.

**`ForcWriterMod.F90`** defines `bgc_forc_config_type` (`f90src/IOutils/ForcWriterMod.F90:19-25`), the singleton `bgc_forc_conf` (`:26`) and the switch `do_bgcforc_write` (`:28`). `WriteBBGCFORC(doy,year)` (`:33-284`) writes one layer's soil state on the configured day. It is configured from `/bbgcforc/` (`drivers/ecosim/EcoSIMAPI.F90:291-297`) and called once per day from the year loop (`:562-566`).

## 6. Output summary

| Channel | Driver call | File name pattern | Cadence control |
|---|---|---|---|
| history tapes 1-3 (configurable) | `hist_htapes_wrapup` (`drivers/ecosim/EcoSIMAPI.F90:542`) | `./<case>.ecosim.h<N>.<date>.nc` | `hist_nhtfrq`, `hist_mfilt`, `hist_fincl1-3` |
| history tapes 4-6 | same | same | compiled defaults only |
| history restart | `hist_restart_ncd` inside `restFile_write` | `.rh<N>.` (`f90src/IOutils/HistFileMod.F90:2329`) | with each state restart |
| state restart | `restFile('write')` (`drivers/ecosim/EcoSIMAPI.F90:548`) | `./<case>.ecosim.r.<date>.nc` | `rest_opt`, `rest_frq` in `/ecosim_time/` |
| batch BGC dump | `WriteBBGCFORC` (`drivers/ecosim/EcoSIMAPI.F90:564`) | `bgc_fname` | `/bbgcforc/` day and layer |

For the meaning of individual tape variables beyond the targets above, the registration calls in `HistData/HistRegister*.F90` carry the authoritative `long_name` and units, and `docs/ecosim-knowledge-base/ecosim_output_info_cb243228.cdl` lists the output variables of a cb243228 tape.
