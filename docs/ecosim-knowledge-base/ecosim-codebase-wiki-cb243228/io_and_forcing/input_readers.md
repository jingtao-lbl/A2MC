---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `drivers/ecosim/EcoSIMAPI.F90` (namelist), `f90src/IOutils/{PlantInfoMod,readimod,readsmod,ReadManagementMod,MicrobeInfoMod}.F90`, `f90src/Modelpars/NitroPars.F90` (microbial file), `f90src/Utils/{fileUtil,ncdio_pio}.F90` (read primitives)
**Last verified:** 2026-10-15
---

# Input Readers

This page documents every input EcoSIM reads before and during a run: the runfile namelist, the grid (site and soil) file, the plant parameter file, the microbial parameter file, the plant management file and the soil management file. Climate and GHG forcing readers are summarised here and detailed in `forcing.md`. The page ends with a reader map for the 60 calibration parameter names used by A2MC EcoSIM cases.

All NetCDF readers use the `ncdio_pio` wrappers (`ncd_pio_openfile`, `ncd_getvar`, `check_var`, `check_ret`, `ncd_pio_closefile`) in `f90src/Utils/ncdio_pio.F90`. Section 5.6 explains what these do when a requested variable is absent, because that behaviour decides whether an incomplete parameter file aborts the run.

## 1. The runfile namelist

### 1.1 How the runfile is read: a fixed 4096-byte buffer

The main program takes the runfile path as its first argument and reads the whole file into a character buffer, `call namelist_to_buffer(nmlfile,nml_buffer)` (`drivers/ecosim/ecosim.F90:77`), then parses it with `call readnamelist(...)` (`drivers/ecosim/ecosim.F90:80`). The buffer length is the parameter `ecosim_namelist_buffer_size = 4096` (`f90src/Utils/fileUtil.F90:25`). `namelist_to_buffer` (`f90src/Utils/fileUtil.F90:125-176`) does one unformatted stream read of 4096 characters (`:143`) and requires that read to hit end of file; if it does not (`nml_error/=-1`), it prints an IO error and calls `abort()` (`:146-150`). A runfile of 4096 bytes or more therefore aborts before any group is parsed. After the read, everything after the last `/` is blanked (`:155-158`).

### 1.2 Namelist groups

| Group | Declared at | Read at | Notes |
|---|---|---|---|
| `/ecosim/` | `drivers/ecosim/EcoSIMAPI.F90:160-169` and `:180-182` (two statements, one group) | `drivers/ecosim/EcoSIMAPI.F90:266-270` in `readnamelist` | Any unknown key makes the read fail and the driver calls `endrun` (`:267-269`). |
| `/bbgcforc/` | `drivers/ecosim/EcoSIMAPI.F90:185-186` | `:272-276` | Batch soil-BGC dump (`ForcWriterMod`); must be present (read failure aborts). |
| `/FixClimForc/` | `drivers/ecosim/EcoSIMAPI.F90:188` | `:319-323`, only when `fixClime` is true (`:317`) | Constant-climate values copied into `clim_var` (`:330-335`). |
| `/ecosim_time/` | `f90src/Utils/ecosim_time_mod.F90:240-241` | via `etimer%Init(nml_buffer,...)` (`drivers/ecosim/EcoSIMAPI.F90:290`) | `delta_time, stop_n, stop_option, rest_frq, rest_opt, diag_frq, diag_opt`. |
| `/Microbes/` | `f90src/Modelpars/MicrobeConfigMod.F90:17-22` | `call ReadMicrobeNamelist(nml_buffer)` (`drivers/ecosim/EcoSIMAPI.F90:338`) | Number of guilds per microbial functional group. |

### 1.3 `/ecosim/` input-file keys

Each key is a module variable of `EcoSIMCtrlMod`; `readnamelist` overwrites the declaration default before the read (`drivers/ecosim/EcoSIMAPI.F90:243-261`). The "disable token" column is what the reader actually tests; the tokens are not uniform.

| Key | Declared | Effective default | Reader (routine, file:line) | Disable token |
|---|---|---|---|---|
| `pft_file_in` | `f90src/Modelconfig/EcoSIMCtrlMod.F90:99` | `''` (`drivers/ecosim/EcoSIMAPI.F90:244`) | `ReadPlantTraitTable` opens it (`f90src/IOutils/PlantInfoMod.F90:1715`); dimensions read earlier by `InitVegPars` (`f90src/Modelpars/PlantBGCPars.F90:200-202`) | `''` (or ATS coupling with `plant_model`) sets one PFT record (`f90src/Modelpars/PlantBGCPars.F90:192-194`); a non-existent path aborts (`:196-198`) |
| `pft_mgmt_in` | `f90src/Modelconfig/EcoSIMCtrlMod.F90:100` | `'NO'` (`drivers/ecosim/EcoSIMAPI.F90:246`) | `ReadPlantInfoNC` (`f90src/IOutils/PlantInfoMod.F90:1531`), `ReadPlantManagementNC` (`:409`), plant half of `ReadFire` (`f90src/IOutils/ReadManagementMod.F90:573`) | `''` only (`f90src/IOutils/PlantInfoMod.F90:407`, `:1518`). The default `'NO'` is opened as a file name and aborts when `plant_model` is true. |
| `grid_file_in` | `f90src/Modelconfig/EcoSIMCtrlMod.F90:101` | `''` (`drivers/ecosim/EcoSIMAPI.F90:245`) | `readi` (`f90src/IOutils/readimod.F90:78`) | none (required) |
| `clm_hour_file_in` | `f90src/Modelconfig/EcoSIMCtrlMod.F90:102` | `''` | `ReadClimNC` hourly branch (`f90src/IOutils/ClimReadMod.F90:793`); span probed by `get_clm_years` (`:1023`) | `''` (no hourly data) |
| `clm_day_file_in` | `f90src/Modelconfig/EcoSIMCtrlMod.F90:103` | `''` | `ReadClimNC` daily branch (`f90src/IOutils/ClimReadMod.F90:727`); `get_clm_years` (`:1010`) | `''` (no daily data) |
| `clm_factor_in` | `f90src/Modelconfig/EcoSIMCtrlMod.F90:105` | `'NO'` (`drivers/ecosim/EcoSIMAPI.F90:243`) | `ReadClimateCorrections` (`f90src/IOutils/readsmod.F90:252`) | `'NO'` (`f90src/IOutils/readsmod.F90:268`). Read but never applied: see `forcing.md` §4.3. |
| `soil_mgmt_in` | `f90src/Modelconfig/EcoSIMCtrlMod.F90:104` | `'NO'` (`drivers/ecosim/EcoSIMAPI.F90:249`) | `ReadManagementFiles` (`f90src/IOutils/ReadManagementMod.F90:435`), soil half of `ReadFire` (`:541`) | `'NO'` (`f90src/IOutils/readsmod.F90:241`); fire mode with `'NO'` aborts (`f90src/Disturbances/FireMod.F90:91-92`) |
| `atm_ghg_in` | `f90src/Modelconfig/EcoSIMCtrlMod.F90:106` | `''` (`drivers/ecosim/EcoSIMAPI.F90:250`) | `GetAtmGts` (`f90src/IOutils/ClimReadMod.F90:943`) | none; opened every year |
| `micpar_file_in` | `f90src/Modelconfig/EcoSIMCtrlMod.F90:107` | `''` (`drivers/ecosim/EcoSIMAPI.F90:261`) | `NitroPars::ReadPars` (`f90src/Modelpars/NitroPars.F90:282`) | `''` (`f90src/Modelpars/NitroPars.F90:280`): compiled defaults are used |

### 1.4 Runtime switches added on `fix/r2-plant-balance`

Both are `logical` module variables of `EcoSIMCtrlMod`, appended to the second `/ecosim/` statement (`drivers/ecosim/EcoSIMAPI.F90:180-182`). A runfile that omits them leaves the `.false.` initialiser in place, so older runfiles reproduce the previous behaviour.

| Switch | Declaration and default | Namelist group | Effect when `.true.` |
|---|---|---|---|
| `guard_floor_dying_stand` | `logical :: guard_floor_dying_stand = .false.` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:41`) | `/ecosim/` (`drivers/ecosim/EcoSIMAPI.F90:182`) | Floors the carbon-pool denominator of the leaf nutrient-withdrawal division at `CPOOL_DIV_FLOOR_dying = 1.0e-12` (`f90src/Plant_bgc/PlantBranchMod.F90:309`; parameter at `f90src/Modelconfig/EcoSIMCtrlMod.F90:53`) and skips the relative plant-carbon balance test when total vegetation carbon is below `VEGC_BAL_FLOOR_dying = 1.0` gC m-2 (`f90src/Plant_bgc/PlantBalMod.F90:850`; parameter at `f90src/Modelconfig/EcoSIMCtrlMod.F90:61`). |
| `conserve_root_clamp` | `logical :: conserve_root_clamp = .false.` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:46`) | `/ecosim/` (`drivers/ecosim/EcoSIMAPI.F90:182`) | When `GrowFibrous1stRootAxes` clamps a negative structural root pool, the uncovered deficit is charged up the axis by `ChargeRootDeficitUpAxis` (`f90src/Plant_bgc/RootMod.F90:3255`, `:3265`). |

Other control keys in `/ecosim/` that change what the readers do: `plant_model`, `microbial_model`, `soichem_model` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:70-72`), `ldo_sp_mode` (`:80`, forces `plant_model` on and microbes and chemistry off, `drivers/ecosim/EcoSIMAPI.F90:307-312`), `iselect_plantZ` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:64`, restricts planting to one PFT, `f90src/IOutils/PlantInfoMod.F90:197`), `first_topou` and `first_pft` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:67-68`), `disp_planttrait` (effective default `.false.`, `drivers/ecosim/EcoSIMAPI.F90:216`; writes a `<case>.plant_trait.desc.<year>` listing, `f90src/IOutils/PlantInfoMod.F90:83-87`), `fixClime` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:114`), `warming_exp` (`:98`), `FireEvents` (local, passed to `config_fire`, `drivers/ecosim/EcoSIMAPI.F90:316`), the atmospheric mixing ratios `aco2_ppm` to `anh3_ppm` (`:251-257`) and the GHG pins `atm_co2_fix`, `atm_ch4_fix`, `atm_n2o_fix` (`:258-260`, positive value pins the series).

### 1.5 `forc_periods`: forcing-year cycling

`forc_periods` is `integer :: forc_periods(15)` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:123`), read as up to five triplets `(first forcing year, last forcing year, repeats)`. The default sets three triplets (`drivers/ecosim/EcoSIMAPI.F90:227`). The main loop runs each triplet `repeats` times over its year range, stepping backwards when the first year exceeds the last (`drivers/ecosim/ecosim.F90:140-167`); each simulated year carries both a forcing year `frectyp%yearclm` and a model year `frectyp%yearcur` (`:151-152`). Readers keyed on the forcing year (`yeari`) replay its climate and, for some management modes, its management.

## 2. Site and grid file: `readimod.F90`

`readi` (`f90src/IOutils/readimod.F90:62-97`) is called once from the main program (`drivers/ecosim/ecosim.F90:103`). It opens `grid_file_in` (`f90src/IOutils/readimod.F90:78`), calls `readsiteNC` (`:80`) and `readTopoNC` (`:82`), and closes the file (`:94`). It no longer opens text log files.

`readsiteNC` (`f90src/IOutils/readimod.F90:195-363`) reads site scalars at record 1: `ALATG, ALTIG, ATCAG, IDTBLG, IETYPG, DTBLIG, DTBLDIG, DTBLGG` (`:230-238`), the twelve lateral boundary conditions `RCHQ*G, RCHG*UG, RCHG*TG, RCHGDG` (`:240-252`) and grid widths `DHI, DVI` (`:254-255`). Six optional bioaerosol partition fractions `fAeroDOM, fAeroDeadMB, fAeroLiveMB, fAeroMoss, fAeroLich, fAeroDeadNMB` are read through `read_aerosol_vars` (`:257-262`), which tests presence with `check_var` and defaults a missing one to zero (`:175-191`). `IETYPG` becomes `KoppenClimZone_col` (`:322`), which selects the plant parameter row (section 5.4). Atmospheric mixing ratios come from the namelist values, not constants: `OXYE_col = ao2_ppm`, `CO2EI_col = aco2_ppm`, `CH4E_col = ach4_ppm`, `Z2OE_col = an2o_ppm` and so on (`:315-321`); CO2, CH4 and N2O are then overwritten every year by `GetAtmGts` (`f90src/IOutils/ClimReadMod.F90:989-992`).

`readTopoNC` (`f90src/IOutils/readimod.F90:367-848`) loops over topographic units, reading slope, aspect and initial snow depth (`:406-408`), the optional `fAeroScalar` (`:399`, `:410-412`), and per unit `PSIFC, PSIWP, ALBS, PH0`, surface-residue C, N and P by complex, `IXTYP1/2, NUI, NJ, NL1, NL2, ISOILR` (`:438-457`), then soil-profile arrays from `CDPTH` onwards (`:470`). `ALBS` fills `SoilAlbedo_col` (`:440`), whose declaration comment says "snowpack albedo" (`f90src/Ecosim_datatype/SnowDataType.F90:15`) although it is the soil-surface albedo. `NJ` is the maximum rooting layer `MaxNumRootLays_col` (`f90src/IOutils/readimod.F90:454`), and `NK_col = MaxNumRootLays_col+1` (`:460`).

## 3. Annual climate and soil-management dispatch: `readsmod.F90`

`ReadClimSoilForcing(yearc,yeari,...)` (`f90src/IOutils/readsmod.F90:83-247`) runs each simulated year from `AdvanceModelOneYear` (`drivers/ecosim/EcoSIMAPI.F90:429`). In order: `ReadClimateCorrections(yeari)` (`f90src/IOutils/readsmod.F90:108`); either `SetConstClimeForcing` under `fixClime` or `ReadClimateForc` when the forcing year changed (`:169-178`); zeroing of the 366-day management arrays (`:185-229`); `ReadFire` when a fire event matches (`:235-239`); `ReadManagementFiles(yeari)` unless `soil_mgmt_in` is `'NO'` (`:241-243`); and `GetAtmGts(yearc,...)` keyed on the MODEL year (`:246`).

## 4. Climate and GHG readers (summary)

`ReadClimNC` (`f90src/IOutils/ClimReadMod.F90:696-895`) reads either the daily or the hourly file according to `get_forc_step_type(yeari)` (`:1036-1062`): daily when daily data exist and the year precedes the first hourly year, hourly otherwise. `GetAtmGts` (`:926-996`) reads twelve monthly CO2, CH4 and N2O values but applies the January value for the whole year. Variables, units and the unit-conversion asymmetry between the daily and hourly paths are in `forcing.md` §2.

## 5. Plant parameter file (`pft_file_in`): `PlantInfoMod.F90`

### 5.1 Call graph

1. Initialisation: `InitPlantTraitTable` sizes the tables from the file dimensions `npfts`, `npft`, `nkopenclms` (`f90src/Modelpars/PlantBGCPars.F90:200-202`, inside `InitVegPars`) and allocates every `*_tab` array (`AllocPlantTraitTable`, `f90src/Ecosim_datatype/PlantTraitTableMod.F90:142-281`).
2. `ReadPlantTraitTable` (`f90src/IOutils/PlantInfoMod.F90:1708-1849`) is called once, `if(plant_model .and. .not. ats_cpl_mode) call ReadPlantTraitTable()` (`f90src/Main/InitEcoSIM.F90:37`). It reads every trait as a whole vector over the `npfts` records into `*_tab` arrays and closes the file (`f90src/IOutils/PlantInfoMod.F90:1847`).
3. Every simulated year, `ReadPlantInfo` (`f90src/IOutils/PlantInfoMod.F90:40-61`; called from `drivers/ecosim/EcoSIMAPI.F90:424` when `plant_model`) calls `ReadPlantInfoNC` (`:52`), which reads only `pft_mgmt_in` to get each column's PFT names, then `readq` (`:57`).
4. `readq` (`f90src/IOutils/PlantInfoMod.F90:64-108`) reads management (`:81`) and, for every PFT `NZ` of every column, calls `ReadPlantProperties` (`:98`).
5. `ReadPlantProperties` (`:472-537`) calls `SetPlantTraits` (`:489`), which copies `*_tab(loc)` into the per-PFT model arrays (`:711-850`), then applies the unit rescaling of section 5.5 (`:507-533`).

Because steps 3 to 5 repeat every year, every `*_pft` trait is re-copied from the table at each year boundary. Quantities derived once in STARTQ (first simulated year only, `drivers/ecosim/EcoSIMAPI.F90:434-438`) are not refreshed.

### 5.2 Two reader routines, and which one runs

| Routine | Lines | Reads into | Callers at cb243228 | Status |
|---|---|---|---|---|
| `ReadPlantTraitTable` | `f90src/IOutils/PlantInfoMod.F90:1708-1849` | `*_tab(npfts)` vectors in `PlantTraitTableMod` | `f90src/Main/InitEcoSIM.F90:37` | LIVE |
| `ReadPlantTraitsNC` | `f90src/IOutils/PlantInfoMod.F90:540-694` | `*_pft(NZ,NY,NX)` directly, one record `loc` per call | none (`git grep -n -i ReadPlantTraitsNC cb243228 -- f90src drivers` finds only its own header and end) | DEAD |

Nothing selects between them at run time: the call graph does. `ReadProperties` calls `SetPlantTraits` (`f90src/IOutils/PlantInfoMod.F90:489`) and no code calls `ReadPlantTraitsNC`; this was already so at 2dea74d9. The dead routine still reads names the live one does not (notably `RSRA` at `:625`) and omits names the live one reads (`ARSRA`, `RSSA`, `CYTOS`, `MRTFQ`, `STDENS`, `CNLCRT`, `CNDCRT`, `CPLCRT`, `CPDCRT`, `MOPHGEN`, `PhiMEAN`, `PhiMIN`, `PhiMAX`, `R95MAT`). Editing a name that only the dead routine reads has no effect on a run.

### 5.3 The live table reader

Every call has the form `call ncd_getvar(pft_nfid, 'NAME', NAME_tab)` with no record index, so each variable is read whole along `npfts` (the shipped file has `npfts = 83` and stores each trait as a 1-D `(npfts)` vector, `CLASS` as `(npfts, JLI)`). Integer type flags come first (`ICTYP`, `IEBTYP`, `IGTYP`, `ISTYP`, `IDTYP`, `INTYP`, `IWTYP`, `IPTYP`, `IBTYP`, `I2EXP`, `IRTYP`, `MY`, `f90src/IOutils/PlantInfoMod.F90:1722-1733`), then photosynthesis (`:1736-1749`), optics (`:1750-1753`), phenology and xylem (`:1754-1768`), morphology and seed (`:1769-1784`), roots and uptake (`:1785-1813`), growth yields (`:1814-1822`) and N:C and P:C stoichiometry (`:1823-1846`). No call is guarded by `check_var`: every name in this list must be in the file.

### 5.4 Selecting a row: `get_pft_loc` and the PFT key

`ReadPlantInfoNC` builds each PFT's key as the first four characters of `pft_type` from `pft_mgmt_in` plus the column's Koppen zone written with format `(I2)` (`f90src/IOutils/PlantInfoMod.F90:1601-1604`), stored in `DATAP` (`:1629`). `SetPlantTraits` passes `DATAP(NZ,NY,NX)(1:6)` to `get_pft_loc` (`:711`), which returns the first index whose `pfts` entry matches (`:1876-1880`). The shipped file's keys look like `gr3s32`, `gr3s35`, `bush31` (4-character code plus 2-digit Koppen zone). The search loop has no upper bound (`:1877-1880`): a key absent from the table runs past the end of `pftss_tab` instead of stopping with a message. So the same PFT code reads a different row under a different `IETYPG` in the grid file.

### 5.5 Rescaling applied after the copy (`ReadPlantProperties`)

| Variable (file name) | Operation | Citation |
|---|---|---|
| `VmaxSpecRubCarboxyRef_pft` (VCMX), `VmaxRubOxyRef_pft` (VOMX), `VmaxPEPCarboxyRef_pft` (VCMX4) | multiplied by 1.92 | `f90src/IOutils/PlantInfoMod.F90:507-509` |
| `SpecLeafChlAct_pft` (ETMX) | multiplied by 1.35 | `f90src/IOutils/PlantInfoMod.F90:510` |
| `MatureGroup_pft` | `= GROUPX_pft - ShootNodeNumAtPlanting_pft` (GROUPX minus XTLI) | `f90src/IOutils/PlantInfoMod.F90:514-515` |
| `RefNodeInitRate_pft` (XRNI), `RateRefLeafAppearance_pft` (XRLA), `MatureGroup_pft`, `ShootNodeNumAtPlanting_pft` (XTLI) | divided by `MaxNodesPerBranch` when `iPlantTurnoverPattern_pft` (IBTYP) is not 0 | `f90src/IOutils/PlantInfoMod.F90:517-522` |
| `HourReq4LeafOut_brch`, `HourReq4LeafOff_brch` from VRNLI, VRNXI | perennial evergreen (`IWTYP` evergreen and `ISTYP` perennial): `AMIN1(4380, VRNLI + 144*ZTYPI*(NB-1))`; otherwise `VRNLI` for every branch | `f90src/IOutils/PlantInfoMod.F90:524-533` |

`ReadPlantProperties` also aborts when a drought-deciduous phenology type is combined with an embryophyte type outside 2 to 4 (`f90src/IOutils/PlantInfoMod.F90:492-500`). `SetPlantTraits` replaces a negative critical photoperiod `XDL` with the site's maximum day length (`:852-854`).

### 5.6 What happens when a requested name is missing

Every `ncd_getvar_*` overload first calls `check_var` and then `nf90_get_var`, for example `ncd_getvar_real_sp_all_1d` (`f90src/Utils/ncdio_pio.F90:1267-1287`) and `ncd_getvar_real_sp` (`:1413-1438`). `check_var` (`:361-406`) only tries `nf90_inq_varid`; on failure it writes `CHECK_VAR: variable <name> is not on initial dataset` to the log and sets `readvar = .false.` (`:397-403`). It does not abort, and the getter ignores the flag. The getter then calls `nf90_get_var` with `vardesc%varID`, which `check_var` never set (the `Var_desc_t` type has no default initialisation, `:223-227`). A netCDF error from that call goes to `check_ret` (`:444-469`), which calls `endrun` (`:466`). In practice a bare `ncd_getvar` of a missing name aborts the run, but because the id is undefined rather than invalid, the source does not guarantee an abort. The reliable pattern is the guarded read used for optional variables: `check_var(...)` then `if(readvar) call ncd_getvar(...)`, as in `NitroPars.F90:363-364`, `readimod.F90:183-189` and `ClimReadMod.F90:820-825`.

### 5.7 Why the model's own default files lack RSRA and SPOSC and still run

`input_data/ecosim_pftpar_20260915.nc` contains 131 variables and lacks `RSRA`, but `RSRA` is read only by the dead `ReadPlantTraitsNC` (`f90src/IOutils/PlantInfoMod.F90:625`), so the live reader never asks for it. The variable it would have filled, `RootSingleVesselRstaxial_pft`, is computed in STARTQ, `InitPlantPhenoMorphoBio`, from ARSRA, `Rax_ref` and RVSR: `RootSingleVesselRstAxial_pft = AlphaVesselAxialResist_pft*Rax_ref*(1.e-6_r8/RootVesselRadius_pft)**4` (`f90src/Ecosim_mods/StartqMod.F90:580`; `Rax_ref = 7.11e11` at `f90src/Modelpars/PlantBGCPars.F90:120`). `input_data/MicrobePars.20260211.nc` contains 76 variables and lacks `SPOSC`, but `SPOSC` is the one microbial name read behind `check_var` (`f90src/Modelpars/NitroPars.F90:363-364`), and `initNitroPars` sets its default unconditionally before reading (`:162-166`).

## 6. Microbial parameter file (`micpar_file_in`): `NitroPars::ReadPars`

`MicrobeInfoMod.F90` is a stub with one empty routine `WriteMicrobeTraits` (`f90src/IOutils/MicrobeInfoMod.F90:15-18`); it reads nothing. The microbial file is read by the function `ReadPars` (`f90src/Modelpars/NitroPars.F90:269-370`). Call chain: `InitModules` → `initNitro` (`f90src/Main/InitEcoSIM.F90:45`) → `initNitro1Layer` → `call initNitroPars` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:68`) → `if(.not.ReadPars())` (`f90src/Modelpars/NitroPars.F90:168`).

- If `micpar_file_in` is empty, `ReadPars` returns `.false.` at once (`:280`) and the fallback block assigns every parameter a compiled value (`:169-248`).
- Otherwise it opens the file (`:282`) and reads 72 scalars and two 2-element vectors (`SPORC`, `SPOMC`) with 74 bare `ncd_getvar` calls (`:284-366`); a missing name follows section 5.6.
- `SPOSC` is the only guarded read: `call check_var(ncfid,'SPOSC',vardesc_SPOSC,readv_SPOSC,print_err=.false.)` then `if(readv_SPOSC) call ncd_getvar(ncfid,'SPOSC',SPOSC_in)` (`:363-364`). The default 4x5 array is set before the read, unconditionally (`:162-166`). `MicBGCPars::SetPars` copies it, `SPOSC = SPOSC_in` (`f90src/Modelpars/MicBGCPars.F90:344`), then multiplies the litter complexes by 1.5 (`:346`). `SetPars` runs from `InitControlParms` (`f90src/Ecosim_mods/StartsMod.F90:746`, via `InitSOMConsts`), after `initNitroPars`.
- Compiled constants, never read from the file: `H2KI = 1.0` and `OAKI = 12.` (`f90src/Modelpars/NitroPars.F90:146-147`; `OAKI` is reassigned to 12 in the fallback at `:179`), plus `ORAD`, `BIOS`, `BIOA`, `FMN` (`:142-145`). The shipped `MicrobePars.20260211.nc` carries `H2KI` and `OAKI`, so editing them there has no effect. `H2KI` and `OAKI` normalise the Gibbs free-energy terms of fermenters and methanogens (`f90src/Microbial_bgc/Box_Micmodel/FermenterMod.F90:108-110`, `AcetogFermentCatabolism`; `f90src/Microbial_bgc/Box_Micmodel/MethanogenMod.F90:93`, `AcetoMethanogenCatabolism`).
- Name collision: the file's `VMXO` fills `NitroPars::VMXO`, used by aerobic heterotrophs (`f90src/Microbial_bgc/Box_Micmodel/AerobicBacteriaMod.F90:160`, `AerobicHeteroBactCatabolism`). A different module variable `PlantBGCPars::VMXO` (nodule N2-fixer respiration, `f90src/Modelpars/PlantBGCPars.F90:79`) is set to 0.125 in `InitVegPars` (`:284`) and used by `NoduleBGCMod`, which `use`s `PlantBGCPars` (`f90src/Plant_bgc/NoduleBGCMod.F90:18`, `:171`). The microbial file does not reach it.

## 7. Plant management (`pft_mgmt_in`): planting, cuts and harvest

`ReadPlantManagementNC` (`f90src/IOutils/PlantInfoMod.F90:386-469`) reads `pft_dflag` (`:411-414`) and branches:

| `pft_dflag` | Behaviour | Citation |
|---|---|---|
| 0, constant | first simulated year (`IGO==0`): planting only, then `InitPlantMgmnt` resets all cut events; later years: management only | `f90src/IOutils/PlantInfoMod.F90:420-430`; `IGO` set at `drivers/ecosim/ecosim.F90:154` |
| 1, transient | record whose `year` equals the FORCING year `yeari`; planting and management | `f90src/IOutils/PlantInfoMod.F90:432-443` |
| other | record whose `year` equals the MODEL year `yearc`; planting and management | `f90src/IOutils/PlantInfoMod.F90:444-455` |

With `pft_dflag = 0`, cut and harvest events are therefore not applied in the first simulated year. Under `pft_dflag = 1`, spin-up cycles that replay a forcing year replay its management.

**Planting** (`readplantinginfo`, `f90src/IOutils/PlantInfoMod.F90:110-211`). Each PFT record in `pft_pltinfo` holds `DDMMYYYY population depth [maximum population]` (3 or 4 whitespace-separated items, `:163-173`); anything else aborts (`:181-185`). A PFT with live population above 0.01 is skipped (`:157`). The ordinal day is `30*(IMO-1)+ICOR(IMO-1)+IDX+LPY` (`:190-194`); `iDayPlanting_pft`, `iYearPlanting_pft` (the record's year is replaced by the current model year), `PPatSeeding_pft = PPI_pft` and `PlantinDepz_pft` are set (`:198-203`).

**Cuts and harvest** (`ReadPlantMgmtinfo`, `f90src/IOutils/PlantInfoMod.F90:243-383`). Up to 24 events per PFT (`nmgnts`, `pft_mgmt`, `:275-292`). Each event string is read as `DY, ICUT, JCUT, HCUT, PCUT, ECUT11, ECUT12, ECUT13, ECUT14, ECUT21, ECUT22, ECUT23, ECUT24` (`:307-308`). Assignments on the event day `IDY` (`:332-349`):

| Field | Model array | Meaning (source comments `:324-345`) |
|---|---|---|
| `ICUT` | `iHarvstType_pft(NZ,IDY,NY,NX)` | event category: 0 to 2 cutting (HCUT > 0 cutting height, < 0 fraction of LAI removed), 3 pruning, 4 or 6 grazing/insects, 5 fire |
| `JCUT` | `jHarvstType_pft` | PFT-specific operation; `JCUT==1` also sets the harvest (termination) day and year (`:319-323`) |
| `HCUT` | `CanopyCutProxy_pft` | cutting height or LAI fraction |
| `PCUT` | `THIN_pft` | fraction of population removed (types 0-3, 5) or specific herbivory rate (types 4, 6) |
| `ECUT11..ECUT14` | `FracBiomHarvsted(iHarvst_pft, leaf/fine non-leaf/stalk/standing dead, ...)` | fraction of each organ removed from the PFT |
| `ECUT21..ECUT24` | `FracBiomHarvsted(iHarvst_col, ...)` | fraction removed from the ecosystem; PFT-level minus ecosystem-level becomes litter |

Grazing and herbivory events come in pairs; days between a pair are filled with the same values (`:351-374`). `InitPlantMgmnt` (`:214-241`) resets every day to type -1, `CanopyCutProxy_pft = 1e6`, `THIN_pft = -1` and all harvest fractions to 1. Fire events reuse the same 13-field record format through `ReadPlantFireMgmt` (`f90src/IOutils/ReadManagementMod.F90:603-685`).

## 8. Soil management (`soil_mgmt_in`) and fire

`ReadManagementFiles(yeari)` (`f90src/IOutils/ReadManagementMod.F90:411-522`) opens `soil_mgmt_in` (`:435`), returns if the `year` dimension is empty (`:437-441`), finds the forcing year and aborts if it is absent (`:444-451`), then per topographic unit reads the sub-variable names `fertf`, `tillf`, `irrigf` and dispatches unless a name is `'NO'`: `ReadTillageFile` (`:500-503`), `ReadFertlizerFile` (`:507-510`), `ReadIrrigationFile` with `Lirri_auto = irrigf(1:4)=='auto'` (`:514-518`).

- Tillage (`ReadTillageFile`, `:36-99`): records `DDMMYYYY, IPLOW, DPLOW` fill `iSoilDisturbType_col` and `DepzCorp_col` per day (`:84-95`); type 1-20 tillage, 21 litter removal, 22 fire, 23-24 drainage (`:70`).
- Fertilizer (`ReadFertlizerFile`, `:279-407`): fills `FERT(ifert_*,IDY,NY,NX)` for broadcast and banded NH4, NH3, urea, NO3 (`:362-369`), phosphates (`:374-376`), lime and gypsum (`:380-381`), plant residue and manure C, N, P (`:385-390`), PO4 (`:391-392`), application depth `FDPTH` (`:396`) and amendment types `IYTYP` (`:401-403`).
- Fire (`ReadFire`, `:526-600`): reads the soil fire schedule from `soil_mgmt_in` through `ReadTillageFile` (`:568`) and the plant fire schedule from `pft_mgmt_in` through `ReadPlantFireMgmt` (`:573-595`).

## Calibration parameters: reader map

Columns: name in the file; file surface; Fortran variable the value ends in; every reader path with routine and file:line (LIVE = `ReadPlantTraitTable` into the `_tab` vector, COPY = `SetPlantTraits` into the per-PFT array, DEAD = `ReadPlantTraitsNC`, never called; microbial = `ReadPars`); dimension; notes. All plant reads are in `f90src/IOutils/PlantInfoMod.F90`; all microbial reads in `f90src/Modelpars/NitroPars.F90`. Plant dimensions: `_tab(npfts)` then `_pft(JP,JY,JX)` unless stated; `(jroots,JP,JY,JX)` arrays receive the file value in the plant-root slot `ipltroot = 1` only. "Missing" refers to the shipped `input_data/ecosim_pftpar_20260915.nc` and `input_data/MicrobePars.20260211.nc`. No name in this set is read from the management file.

| File name | Surface | Fortran variable | Reader paths (routine, file:line) | Dimension | Notes |
|---|---|---|---|---|---|
| ARSRA | plant | `AlphaVesselAxialResist_pft` | LIVE `ReadPlantTraitTable` f90src/IOutils/PlantInfoMod.F90:1797; COPY `SetPlantTraits` f90src/IOutils/PlantInfoMod.F90:794; DEAD: not read | per PFT | `[-]`. Used once, in STARTQ `InitPlantPhenoMorphoBio` (f90src/Ecosim_mods/StartqMod.F90:580) to build `RootSingleVesselRstAxial_pft`; not itself sent to the plant kernels. Live axial-resistance lever (with RVSR). |
| CHL | plant | `LeafProtein2Chl_pft` | LIVE `ReadPlantTraitTable` f90src/IOutils/PlantInfoMod.F90:1747 into `LeafChl2Protein_tab`; COPY `SetPlantTraits` :742; DEAD :578 | per PFT | fraction of leaf protein bound to chlorophyll. |
| CKC | microbial | `NitroPars::CKC` | `ReadPars` f90src/Modelpars/NitroPars.F90:295 | scalar | `gC gC-1`; fallback 1.0E-03 only when no file (:182). |
| CNDCRT | plant | `rECDeadCRoot_pft(ielmn,...)` | LIVE :1791 (`rNCDeadCRoot_tab`); COPY :784; DEAD: not read | `(NumPlantChemElms,JP,JY,JX)`, N slot | dead coarse root N:C. |
| CNLCRT | plant | `rECLiveCRoot_pft(ielmn,...)` | LIVE :1790 (`rNCLiveCRoot_tab`); COPY :782; DEAD: not read | element slot N | live coarse root N:C. |
| CNLF | plant | `rNCLeaf_pft` | LIVE :1825; COPY :828; DEAD :659 | per PFT | leaf N:C, `gN gC-1`. |
| CNRSV | plant | `rNCReserve_pft` | LIVE :1829; COPY :832; DEAD :663 | per PFT | stalk reserve N:C. |
| CNRT | plant | `rNCRoot_pft` | LIVE :1833; COPY :836; DEAD :667 | per PFT | root N:C; STARTQ forms `CNRTS_pft = rNCRoot_pft*RootBiomGrosYld_pft` (f90src/Ecosim_mods/StartqMod.F90:513) in the first year only. |
| CNRTLIG | plant | `rNCLigRoot_pft` | LIVE :1828; COPY :831; DEAD :661 | per PFT | lignified root N:C. |
| CNSHE | plant | `rNCSheath_pft` | LIVE :1826; COPY :829; DEAD :660 | per PFT | petiole/sheath N:C. |
| CNSTK | plant | `rNCStalk_pft` | LIVE :1827; COPY :830; DEAD :662 | per PFT | stalk N:C. |
| CNWL | plant | `rProteinC2LeafN_pft` | LIVE :1824; COPY :826; DEAD :655 | per PFT | protein C per leaf N, `gC gN-1`. |
| CNWR | plant | `rProteinC2RootN_pft` | LIVE :1823; COPY :827; DEAD :657 | per PFT | protein C per root N. |
| CPDCRT | plant | `rECDeadCRoot_pft(ielmp,...)` | LIVE :1793 (`rPCDeadCRoot_tab`); COPY :785; DEAD: not read | element slot P | dead coarse root P:C. |
| CPLCRT | plant | `rECLiveCRoot_pft(ielmp,...)` | LIVE :1792 (`rPCLiveCRoot_tab`); COPY :783; DEAD: not read | element slot P | live coarse root P:C; the shipped file's units attribute says `gN gC-1` (metadata typo). |
| CPLF | plant | `rPCLeaf_pft` | LIVE :1838; COPY :842; DEAD :670 | per PFT | leaf P:C. |
| CPWL | plant | `rProteinC2LeafP_pft` | LIVE :1837; COPY :840; DEAD :656 | per PFT | protein C per leaf P, `gC gP-1`. |
| CTC | plant | `TCChill4Seed_pft` | LIVE :1756; COPY :753; DEAD :589 | per PFT | chilling temperature, degC. |
| DCKM0 | microbial | `NitroPars::DCKM0` | `ReadPars` f90src/Modelpars/NitroPars.F90:298 | scalar | `gC g-1 soil`; fallback 1.0E+03 (:185). |
| DMLF | plant | `LeafBiomGrowthYld_pft` | LIVE :1814; COPY :817; DEAD :645 | per PFT | leaf growth yield, `gC gC-1`. |
| DMRSV | plant | `ReserveBiomGrowthYld_pft` | LIVE :1817; COPY :820; DEAD :648 | per PFT | reserve growth yield. |
| DMRT | plant | `RootBiomGrosYld_pft` | LIVE :1821; COPY :824; DEAD :652 | per PFT | root growth yield; also enters `CNRTS_pft`/`CPRTS_pft` in STARTQ (f90src/Ecosim_mods/StartqMod.F90:513-514). |
| DMSTK | plant | `StalkBiomGrowthYld_pft` | LIVE :1816; COPY :819; DEAD :647 | per PFT | stalk growth yield. |
| ETMX | plant | `SpecLeafChlAct_pft` | LIVE :1746 (`SpecChloryfilAct_tab`); COPY :740; DEAD :577 | per PFT | multiplied by 1.35 after the copy (:510). |
| FCO2 | plant | `CanopyCi2CaRatio_pft` | LIVE :1749 (`CanopyCi2CaRatio_pft_tab`); COPY :744; DEAD :580 | per PFT | intercellular:ambient CO2 ratio. |
| GROUPX | plant | `GROUPX_pft` | LIVE :1765; COPY :761; DEAD :595 | per PFT | `MatureGroup_pft = GROUPX - XTLI` (:514-515), then divided by `MaxNodesPerBranch` if IBTYP is not 0 (:520). |
| MRTFQ | plant | `MediumRootBranchFreq_pft` | LIVE :1800; COPY :799; DEAD: not read | per PFT | `m-1`, medium-root branching frequency. |
| OMGR | microbial | `NitroPars::OMGR` | `ReadPars` f90src/Modelpars/NitroPars.F90:291 | scalar | `h-1`; fallback 0.25 (:176). |
| OSMO | plant | `OrganOsmoPsi0pt_pft` | LIVE :1811 (`CanOsmoPsi0pt_tab`); COPY :813; DEAD :641 | per PFT | osmotic potential at zero water potential, MPa. |
| PB | plant | `NonstCMinConc2InitBranch_pft` | LIVE :1764; COPY :759; DEAD :593 | per PFT | nonstructural C needed for branching. |
| PORT | plant | `RootPorosity_pft(1,...)` | LIVE :1787; COPY :789; DEAD :619 | `(jroots,...)`, slot 1 | STARTQ copies it into the mycorrhizal slot (f90src/Ecosim_mods/StartqMod.F90:517). |
| PR | plant | `NonstCMinCon2InitRoot_pft` | LIVE :1794; COPY :792; DEAD :622 | per PFT | nonstructural C needed for root branching. |
| PTSHT | plant | `ShootRootNonstElmConduts_pft` | LIVE :1798 (`ShutRutNonstElmntConducts_tab`); COPY :797; DEAD :626 | per PFT | shoot-root nonstructural transfer conductance, `h-1`. |
| RCS | plant | `RCS_pft` | LIVE :1812; COPY :814; DEAD :642 | per PFT | e-folding turgor for stomatal resistance, MPa. |
| RMOM | microbial | `NitroPars::RMOM` | `ReadPars` f90src/Modelpars/NitroPars.F90:353 | scalar | `gC gN-1 h-1`; fallback 0.010 (:246). |
| RRAD1M | plant | `Root1stMaxRadius_pft(1,...)` | LIVE :1785; COPY :787; DEAD :617 | slot 1 | mycorrhizal slot is a compiled 8.0E-06 m (f90src/Ecosim_mods/StartqMod.F90:515). |
| RRAD2M | plant | `Root2ndMaxRadius_pft(1,...)` | LIVE :1786; COPY :788; DEAD :618 | slot 1 | mycorrhizal slot compiled 2.0E-06 m (StartqMod.F90:516); overwritten with 0.0002 only when `ldo_sp_mode` and `ats_cpl_mode` are both set (f90src/Plant_bgc/UptakesMod.F90:488, `UpdateRootProperty`). |
| RSMX | plant | `CuticleResist_pft` | LIVE :1813; COPY :815; DEAD :643 | per PFT | cuticular resistance, `s m-1`. |
| RSRA | plant | `RootSingleVesselRstaxial_pft` (dead target only) | LIVE: not read; COPY: none; DEAD `ReadPlantTraitsNC` :625 | per PFT | NOT READ on the live path, and missing from the shipped default file. The target variable is computed in STARTQ from ARSRA and RVSR (f90src/Ecosim_mods/StartqMod.F90:580). Silent no-op lever. |
| RSRR | plant | `RootRadialResist_pft(1,...)` | LIVE :1795; COPY :793; DEAD :624 | slot 1 | mycorrhizal slot compiled 1.0E+04 (StartqMod.F90:527); overwritten with 400000 only under `ldo_sp_mode` and `ats_cpl_mode` (f90src/Plant_bgc/UptakesMod.F90:485). |
| RTFQ | plant | `FineRootBranchFreq_pft` | LIVE :1799; COPY :798; DEAD :627 | per PFT | fine-root branching frequency, `m-1`. |
| RUBP | plant | `LeafRubisco2Protein_pft` | LIVE :1743; COPY :738; DEAD :575 | per PFT | fraction of leaf protein in rubisco. |
| SLA1 | plant | `SLA1_pft` | LIVE :1769; COPY :766; DEAD :600 | per PFT | file units `m2 gC-1`; it is the coefficient of a power law in mass. |
| SPOMC | microbial | `NitroPars::SPOMC(2)` | `ReadPars` f90src/Modelpars/NitroPars.F90:355 | 2 (file dim `nactbioms`) | `gC gN-1 h-1`; fallback (1.0E-02, 0.1E-02) (:248). |
| SPORC | microbial | `NitroPars::SPORC(2)` | `ReadPars` f90src/Modelpars/NitroPars.F90:354 | 2 | fallback (7.5, 1.5) (:247). |
| SPOSC | microbial | `NitroPars::SPOSC_in(jskenc,jcplxc)` | `ReadPars`, guarded: `check_var` f90src/Modelpars/NitroPars.F90:363, read :364 | 4 kinetic components x 5 complexes | Missing from `MicrobePars.20260211.nc`; default set unconditionally (:162-166); copied to `micpar%SPOSC` in `SetPars` (f90src/Modelpars/MicBGCPars.F90:344) and multiplied by 1.5 for litter complexes (:346). |
| UPMXPO | plant | `VmaxPO4Root_pft(ipltroot,...)` | LIVE :1808; COPY :809; DEAD :637 | slot 1 | copied into the mycorrhizal slot in STARTQ (f90src/Ecosim_mods/StartqMod.F90:524). |
| UPMXZH | plant | `VmaxNH4Root_pft(ipltroot,...)` | LIVE :1801; COPY :800; DEAD :629 | slot 1 | mycorrhizal copy StartqMod.F90:518. |
| UPMXZO | plant | `VmaxNO3Root_pft(ipltroot,...)` | LIVE :1805; COPY :805; DEAD :633 | slot 1 | mycorrhizal copy StartqMod.F90:521. |
| VCMX | plant | `VmaxSpecRubCarboxyRef_pft` | LIVE :1736 (`VmaxRubCarboxyRef_tab`); COPY :731; DEAD :568 | per PFT | multiplied by 1.92 after the copy (:507). |
| VMXO | microbial | `NitroPars::VMXO` | `ReadPars` f90src/Modelpars/NitroPars.F90:300 | scalar | fallback 0.125 (:189). Not the same variable as `PlantBGCPars::VMXO` (nodules, compiled, f90src/Modelpars/PlantBGCPars.F90:284). |
| VOMX | plant | `VmaxRubOxyRef_pft` | LIVE :1737; COPY :732; DEAD :569 | per PFT | multiplied by 1.92 (:508). |
| VRNLI | plant | local `VRNLI` → `HourReq4LeafOut_brch` | LIVE :1757 (`VRNLI_tab`); COPY :754; DEAD :590 | per branch | hours; banded by branch for perennial evergreens with ZTYPI (:527), plain copy otherwise (:530). |
| VRNXI | plant | local `VRNXI` → `HourReq4LeafOff_brch` | LIVE :1758; COPY :755; DEAD :591 | per branch | as VRNLI (:528, :531). |
| XKCO2 | plant | `XKCO2_pft` | LIVE :1739; COPY :734; DEAD :571 | per PFT | Km of rubisco for CO2, uM. |
| XPPD | plant | `PhotoPeriodSens_pft` | LIVE :1768; COPY :764; DEAD :598 | per PFT | photoperiod sensitivity. |
| XRLA | plant | `RateRefLeafAppearance_pft` | LIVE :1755 (`RefLeafAppearRate_tab`); COPY :752; DEAD :588 | per PFT | divided by `MaxNodesPerBranch` when IBTYP is not 0 (:519). |
| XRNI | plant | `RefNodeInitRate_pft` | LIVE :1754; COPY :751; DEAD :587 | per PFT | divided by `MaxNodesPerBranch` when IBTYP is not 0 (:518). |
| XTLI | plant | `ShootNodeNumAtPlanting_pft` | LIVE :1766; COPY :762; DEAD :596 | per PFT | subtracted from GROUPX (:515); divided by `MaxNodesPerBranch` when IBTYP is not 0 (:521). |
| ZTYPI | plant | `PlantInitThermoAdaptZone_pft` | LIVE :1735; COPY :725; DEAD :566 | per PFT | Copied unchanged. The "banding" in `PlantInfoMod` is display text only (`pft_display`, f90src/IOutils/PlantInfoMod.F90:1092-1103). Numeric uses: `HourReq4Leaf*` (:527-528) and `PFTThermalAcclimation` (f90src/Ecosim_mods/StartqMod.F90:450). |

Line numbers given as `:NNN` in a plant row refer to `f90src/IOutils/PlantInfoMod.F90`; in a microbial row to `f90src/Modelpars/NitroPars.F90`.
