---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/ATSUtils/` (8 files), `drivers/ATSEcoSIM/`, and the ATS-specific branches in `f90src/Main/InitEcoSIM.F90`, `f90src/Modelpars/PlantBGCPars.F90`, `f90src/Prescribed_pheno/PrescribePhenolMod.F90`, `f90src/Plant_bgc/UptakesMod.F90`
**Last verified:** 2026-10-15
---

# ATS-EcoSIM Coupling Layer

In the coupled configuration ATS (the Advanced Terrestrial Simulator) owns the mesh, the flow solver and the time loop. EcoSIM is loaded as a library and called once per ATS step per set of columns. This page covers only the EcoSIM side of the bridge. Everything in `f90src/ATSUtils/` is byte-identical to the 2dea74d9 pin except comment edits in `ATSEcoSIMAdvanceMod.F90`.

The operator-split call pattern:

```
ATS time loop
  EcoSIM_Setup(properties, state, sizes, ...)      once      f90src/ATSUtils/ecosim_wrappers.F90:44-70
     ATS2EcoSIMData -> Init_EcoSIM -> EcoSIM2ATSData
  each step:
  EcoSIM_Advance(delta_t, properties, state, ...)            f90src/ATSUtils/ecosim_wrappers.F90:97-126
     ATS2EcoSIMData(num_columns, state, properties, sizes)   copy ATS arrays into a_* arrays
     Run_EcoSIM_one_step(sizes)                              ATSCPLMod version, surface balance
        SurfaceEBalance -> RunEcoSIMSurfaceBalance(num_cols)
     EcoSIM2ATSData(num_columns, state, sizes)               copy sources and fluxes back
  EcoSIM_Shutdown()                                          empty body, :74-93
```

## 1. Build

`f90src/ATSUtils/CMakeLists.txt` always builds the library `ATSUtils_mods` from the eight sources, and `drivers/ATSEcoSIM/CMakeLists.txt:7` always builds `ATSEcoSIM_test.x` (its lines 9-12 are include directories). The top-level option `ATS_ECOSIM` (`CMakeLists.txt:173-199`) only changes how the library can be linked into ATS: `-fPIC` for C, C++ and Fortran plus `-g -O0 -fbacktrace -fbounds-check` for Fortran (`:194-196`), and NetCDF, HDF5 and zlib from `${TPL_INSTALL_PREFIX}`, which is `$AMANZI_TPLS_DIR` (`:28`, `:183-192`).

## 2. File map

| File | Lines | Role |
|---|---|---|
| `f90src/ATSUtils/ecosim_wrappers.F90` | 126 | Free-standing `bind(C)` entry points `EcoSIM_DataTest` (`:33-40`), `EcoSIM_Setup` (`:44-70`), `EcoSIM_Shutdown` (`:74-93`), `EcoSIM_Advance` (`:97-126`). They sit outside any module to avoid compiler-specific name mangling (header comment). |
| `f90src/ATSUtils/ATSCPLMod.F90` | 375 | `ATS2EcoSIMData` (`:29-240`), `EcoSIM2ATSData` (`:243-308`), `Run_EcoSIM_one_step` (`:312-323`), `Init_EcoSIM` (`:326-339`), `SurfaceEBalance` (`:342-355`), `SetBGCSizes` (`:359-372`) |
| `f90src/ATSUtils/ATSEcoSIMInitMod.F90` | 158 | `Init_EcoSIM_Soil(NYS)` (`:31-155`): sets the mode flags, allocates, copies ATS soil state, calls `startsim` |
| `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90` | 382 | `RunEcoSIMSurfaceBalance(NYS)` (`:45-380`): the per-step orchestrator |
| `f90src/ATSUtils/SharedDataMod.F90` | 209 | The `a_*` dock arrays and scalars; `InitSharedData` (`:88-170`), `DestroySharedData` (`:174-207`) |
| `f90src/ATSUtils/ATSUtilsMod.F90` | 47 | `ComputeDatefromATS` (`:17-46`) |
| `f90src/ATSUtils/BGC_containers.F90` | 225 | `bind(c)` wire types: vector, matrix and tensor primitives (`:77-137`), `BGCSizes` (`:139-143`), `BGCState` (`:145-174`), `BGCProperties` (`:176-218`), `BGCAuxiliaryData` (`:220-223`) |
| `f90src/ATSUtils/c_f_interface_module.F90` | 187 | C and Fortran string helpers adapted from Alquimia: `c_f_string_ptr` (`:49-72`), `c_f_string_chars` (`:74-91`), `f_c_string_ptr` (`:93-117`), `f_c_string_chars` (`:119-139`), `CaseInsensitiveStrcmp` (`:142-173`) |

The field order of the `bind(c)` types is part of the binary interface with the C side, so fields may only be appended (file header). `BGCProperties` carries the three ATS mode flags `p_bool`, `a_bool`, `pheno_bool` as `logical(c_bool)` (`f90src/ATSUtils/BGC_containers.F90:215-217`).

## 3. What ATS switches off, and what it sets in place of the plant trait table

`Init_EcoSIM_Soil` sets the run controls directly instead of reading a runfile (`f90src/ATSUtils/ATSEcoSIMInitMod.F90:54-63`):

| Variable | Value under ATS | Citation |
|---|---|---|
| `ATS_cpl_mode` | `.true.` | `:54` |
| `column_mode` | `.true.` | `:55` |
| `plant_model` | `pheno_bool` (from ATS properties) | `:56` |
| `ldo_sp_mode` | `pheno_bool` | `:57` |
| `microbial_model`, `soichem_model`, `snowRedist_model` | `.false.` | `:58-60` |
| `disp_planttrait`, `disp_modelconfig` | `.false.` | `:61-62` |
| `mod_snow_albedo` | `a_bool` | `:63` |

So under ATS the plant model, when on, always runs in prescribed-phenology (SP) mode, and soil microbes and geochemistry never run.

**The plant trait table is never read.** The standalone path reads it in `InitModules` only when `plant_model .and. .not. ats_cpl_mode` (`f90src/Main/InitEcoSIM.F90:37`). ATS does not call `InitModules` at all (the call is commented out at `f90src/ATSUtils/ATSEcoSIMInitMod.F90:69`); it calls `InitAlloc` and `InitUptake` directly (`:70-71`). Inside `InitAlloc`, `InitPlantTraitTable -> InitVegPars` sees `ats_cpl_mode .and. plant_model` and sets `npfts_tab = 1` without opening `pft_file_in` (`f90src/Modelpars/PlantBGCPars.F90:192-194`, `InitVegPars`). Its `npft` and `nkopenclms` outputs are left unset on this branch.

**What supplies the plant description instead:**

| Quantity | Value under ATS | Citation |
|---|---|---|
| Number of PFTs per column | `NP_col = 1`; `NP0_col` = 1 unless ATS `vegetation_type` is 0 | `f90src/Prescribed_pheno/PrescribePhenolMod.F90:216`; `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:278-282` |
| Root type | `irootType_col = a_VEG` (ATS `vegetation_type`); `PrescribePhenologyInterp` itself uses `irootType = 1` | `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:275`; `f90src/Prescribed_pheno/PrescribePhenolMod.F90:211` |
| Monthly LAI, SAI | hard-coded 12-month example arrays `lai(12)`, `sai(12)` | `f90src/Prescribed_pheno/PrescribePhenolMod.F90:201-202`, assigned at `:219-220` (routine `PrescribePhenologyInterp`) |
| Canopy height | 17 m | `f90src/Prescribed_pheno/PrescribePhenolMod.F90:221`; `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:273` |
| Leaf angle classes | uniform | `f90src/Prescribed_pheno/PrescribePhenolMod.F90:222` |
| Live plant population | `PlantPopuLive_pft = 0.6` ("temporary set TEST values, assuming trees") | `f90src/Prescribed_pheno/PrescribePhenolMod.F90:254-257` |
| Mycorrhizal root types | `Myco_pft = 1` | `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:122` |
| Root axial and radial resistance | `Root2ndAxialResist_pft = 500`, `RootRadialResist_pft = 4.0e5` | `f90src/Plant_bgc/UptakesMod.F90:482-485` (routine `UpdateRootProperty`, SP branch) |
| Root radii | secondary 2.0e-4 m, primary 1.0e-3 m | `f90src/Plant_bgc/UptakesMod.F90:486-493` |
| Soil hydraulic conductivity for root uptake | 0.000571, placeholder | `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:195` |
| Wilting point, field capacity | 0.25, 0.5 | `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:207-208` |
| Latitude, solar noon | 40°, 12 h | `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:145-146` |

ATS does pass LAI and SAI (`ATSCPLMod.F90:175-179`). `a_LAI` is copied into `LAI_col(NX,NY)` (`ATSEcoSIMAdvanceMod.F90:274`), with indices in the opposite order to every other `(NY,NX)` array, and `PrescribePhenologyInterp` does not read it. Under ATS the phenology date comes from `ComputeDatefromATS` (`f90src/Prescribed_pheno/PrescribePhenolMod.F90:227-230`); in the standalone SP path it is fixed to day 1 of January (`:231-238`).

## 4. Data in: `ATS2EcoSIMData` (`f90src/ATSUtils/ATSCPLMod.F90:29-240`)

Each field is mapped with `c_f_pointer` from the C struct onto a Fortran view and copied into a `SharedDataMod` array.

- Per-cell `(cell, column)` fields: temperature (`:61-63`), depth (`:65-67`), dz (`:69-71`), volume (`:73-75`), water content (`:81-83`), bulk, liquid and rock density (`:106-116`), matric pressure (`:118-120`), porosity (`:122-124`), liquid saturation (`:126-128`), hydraulic conductivity (`:135-137`), rooting-depth fraction (`:139-141`), subsurface water and energy sources (`:143-149`). `a_AREA3` is assigned from `props%volume` (`:77-79`), and `a_AreaZ = a_Volume/a_dz` is computed for column 1 only (`:89-91`).
- Per-column fields: column area (`:93-94`), shortwave and longwave radiation (`:151-155`), air temperature (`:157-158`), vapour pressure (`:160-161`), wind (`:163-164`), aspect (`:172-173`), LAI, SAI, vegetation type, snow albedo (`:175-185`), surface water and energy sources, snow depth, canopy longwave, latent and sensible heat, canopy water (`:219-238`).
- Scalars: atmospheric composition, heat capacity, field capacity and wilting-point pressures, `p_bool`, `a_bool`, `pheno_bool`, `current_day`, `current_year` (`:192-206`).
- Precipitation: with `p_bool` ATS sends total precipitation and EcoSIM splits rain and snow at -0.25 °C (`:208-210`; split in `ATSEcoSIMAdvanceMod.F90:250-257`); otherwise ATS sends rain and snow separately (`ATSCPLMod.F90:211-217`).

## 5. One step: `RunEcoSIMSurfaceBalance` (`f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:45-380`)

| Step | What happens | Citation |
|---|---|---|
| 1 | `I = 1; J = 1`; `ComputeDatefromATS`; `yearIJ%year = current_year`, `yearIJ%J = 12`, `yearIJ%I = current_day + 1` | `:93`, `:102`, `:107-109` |
| 2 | `SetMeshATS`; per column zero `QVegET_col`, `SetHourlyAccumulatorsATS`, `NK_col = a_NL`, `Myco_pft = 1`, `NP0_col = 1` | `:111-124` |
| 3 | `PrepHourlyWeather(I, J, ...)`, always with `I = 1, J = 1` | `:127` |
| 4 | Per column: forcing with unit conversions (wind m s-1 to m h-1, shortwave W m-2 to MJ m-2 h-1, vapour pressure Pa to kPa), sky longwave with emissivity 0.684, per-layer soil state from ATS (water m3 from mol, matric pressure Pa to MPa), hydraulic placeholders, rain and snow, phenology inputs | `:128-284` |
| 5 | If `ldo_sp_mode`: `PrescribePhenologyInterp`, then `PlantCanopyRadsModel` per column | `:286`, `:294-298` |
| 6 | `StageSurfacePhysModel` | `:303` |
| 7 | `DO M = 1, NPH`: `RunSurfacePhysModelM`, accumulate ground heat and infiltration, `UpdateSurfaceAtM` | `:317-338` |
| 8 | `SnowMassUpdate` per column | `:339-341` |
| 9 | If `ldo_sp_mode`: `PlantModel(yearIJ, ...)`, which takes the SP branch (`PlantUptakeAPISend`, `ROOTUPTAKES`, `extracts`, `PlantUPtakeAPIRecv`; `f90src/APIs/PlantMod.F90:60-68`) | `:343` |
| 10 | Return sources to ATS units by dividing by `dts_HeatWatTP`; fill canopy, ET and evaporation outputs; per-layer root water uptake into `a_SSWS` | `:345-376` |

The full plant growth, microbial and chemistry stack does not run under ATS. When `pheno_bool` is set, the SP-mode plant water and nutrient uptake does run.

## 6. Data out: `EcoSIM2ATSData` (`f90src/ATSUtils/ATSCPLMod.F90:243-308`)

Writes back subsurface water and energy sources, canopy longwave, boundary latent and sensible heat, canopy water, transpiration, canopy, ground, litter and snow evaporation, sublimation, surface water and energy sources, and snow depth (`:258-306`). Snow temperature is commented out (`:264-265`).

## 7. Date arithmetic (`f90src/ATSUtils/ATSUtilsMod.F90:17-46`)

`ComputeDatefromATS(current_day, current_year, current_month, day_of_month, total_days_in_month)` walks a fixed `days_in_month = [31,28,31,30,...]` table (`:24`) to turn a zero-based day of year into month and day of month. The leap-year line is commented out (`:29`), so the local `is_leap` is never assigned and its value at `:35` is undefined. This is **not** the standalone calendar: the standalone time manager is Gregorian with 366-day leap years (`f90src/Utils/ecosim_time_mod.F90:652-658`). ATS drivers that cross a 29 February should not assume the two agree.

## 8. Initialisation (`Init_EcoSIM`, `Init_EcoSIM_Soil`)

`Init_EcoSIM(sizes)` calls `InitSharedData(size_col, num_cols)` and `Init_EcoSIM_Soil(num_cols)` (`f90src/ATSUtils/ATSCPLMod.F90:326-339`). `InitSharedData` redefines the grid constants `JX = 1`, `JY = ncol`, `JZ = ncells_per_col_` (`f90src/ATSUtils/SharedDataMod.F90:96-97`), allocates the dock arrays, and sets `a_NU = 1`, `a_NL = ncells_per_col_` (`:164-165`).

`Init_EcoSIM_Soil(NYS)` (`f90src/ATSUtils/ATSEcoSIMInitMod.F90:31-155`):

1. Mode flags (section 3; `:54-63`).
2. `SetMeshATS`, `set_ecosim_solver(30, 10, 20, 20)` (`:66-67`).
3. `InitAlloc`, `InitUptake`, allocate `THETRX = (4e-6, 8e-6, 8e-6)` (`:70-73`).
4. Open `snow_debug.txt` (`:76-78`).
5. `FlowDirIndicator_col = 3` (no lateral flow), `MaxNumRootLays_col = 1` (`:80-81`).
6. Per column and layer: copy ATS temperature, depth, porosity, area, bulk density (kg m-3 to Mg m-3) and the `a_CORG*` arrays into EcoSIM state (`:89-142`).
7. Field-capacity and wilting-point pressures (`:144-145`).
8. `startsim` (`:147`), the grid and soil-hydraulics set-up routine (`f90src/Ecosim_mods/StartsMod.F90:1017-1170`). This is the only caller of `startsim`; the standalone driver uses `STARTS`.
9. Restore `AREA_3D(3,L,...) = a_AREA3`, which `startsim` overwrote (`f90src/ATSUtils/ATSEcoSIMInitMod.F90:149-153`).

## 9. Known defects in the coupling layer (code reading, not run-verified)

| Defect | Citation |
|---|---|
| `EcoSIM2ATSData` never sets its local `num_cols` but uses it as the shape of every `c_f_pointer`; `size_procs` is computed and unused | `f90src/ATSUtils/ATSCPLMod.F90:250`, `:256-306` |
| `a_AREA3` is taken from `props%volume`, not an area field | `f90src/ATSUtils/ATSCPLMod.F90:77-79` |
| `sizes` is `intent(out)` in `EcoSIM_Setup`, `EcoSIM_Advance` and `ATS2EcoSIMData`, but `ATS2EcoSIMData` reads `sizes%ncells_per_col_` | `f90src/ATSUtils/ecosim_wrappers.F90:56`, `:115`; `f90src/ATSUtils/ATSCPLMod.F90:35`, `:54` |
| `a_CORGC`, `a_CORGN`, `a_CORGP` are allocated but never filled from ATS, then copied into soil organic matter | `f90src/ATSUtils/SharedDataMod.F90:30`, `:108`; `f90src/ATSUtils/ATSEcoSIMInitMod.F90:134-136`; `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:170-172` |
| `SoilBulkDensity_vr` is assigned as a whole array inside the layer loop | `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:169` |
| `LAI_col(NX,NY)` index order reversed | `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:274` |
| Weather prepared for day 1, hour 1 every step | `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:93`, `:127` |
| `SnowMassUpdate` receives the uninitialised locals `Qinfl2MicPM`, `Hinfl2SoilM` | `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:340` |
| `ComputeDatefromATS` reads an unassigned `is_leap` | `f90src/ATSUtils/ATSUtilsMod.F90:26-35` |
| `delta_t` is accepted and ignored; the surface sub-cycling sets its own step | `f90src/ATSUtils/ecosim_wrappers.F90:112` |
| `EcoSIM_Shutdown` does nothing; `DestroySharedData` is never called | `f90src/ATSUtils/ecosim_wrappers.F90:74-93`; `f90src/ATSUtils/SharedDataMod.F90:174-207` |

## 10. The in-process test driver (`drivers/ATSEcoSIM/ATSEcoSIM_test.F90`, 181 lines)

`program EcoATSTest` sets `NYS = 1`, `ncells_per_col_ = 100`, fills `sizes` by hand, sets `a_bool = .false.` and `pheno_bool = .true.` (`drivers/ATSEcoSIM/ATSEcoSIM_test.F90:21-31`), allocates and fills the `a_*` arrays with synthetic values in `Init_ATSEcoSIM_driver` (`:32`, routine from `:51`), calls `Init_EcoSIM` (`:34`), then runs six steps of `Run_EcoSIM_one_step` with `p_rain = 1.0e-3` (`:36-45`). It never goes through `ATS2EcoSIMData`, so it does not exercise the C struct mapping. The values it sets are test inputs, not defaults.

## 11. Confusable names

| Name | Module | Location | What it does |
|---|---|---|---|
| `Run_EcoSIM_one_step(yearIJ, NHW, NHE, NVN, NVS)` | `EcoSIMAPI` (private) | `drivers/ecosim/EcoSIMAPI.F90:37-128` | Full hourly physics sequence of the standalone model |
| `Run_EcoSIM_one_step(sizes)` | `ATSCPLMod` (public) | `f90src/ATSUtils/ATSCPLMod.F90:312-323` | Calls `SurfaceEBalance` -> `RunEcoSIMSurfaceBalance` |
| `starts` vs `startsim` | `StartsMod` | `f90src/Ecosim_mods/StartsMod.F90:1017` (`startsim`) | `STARTS` is the standalone soil initialiser; `startsim` is the ATS one |

## Cross-references

- Standalone driver and SP mode: `ecosim_main.md` §2.6.
- Surface physics routines called here (`StageSurfacePhysModel`, `RunSurfacePhysModelM`, `UpdateSurfaceAtM`, `SnowMassUpdate`): the hydrotherm section of this wiki.
- The standalone plant trait reader that ATS bypasses: `../io_and_forcing/input_readers.md`.
