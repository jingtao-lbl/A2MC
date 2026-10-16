---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/APIs/` (13 files), `f90src/APIData/` (14 files); callers in `drivers/ecosim/EcoSIMAPI.F90`, `f90src/Modelforc/Hour1Mod.F90`, `f90src/Main/InitEcoSIM.F90`, `f90src/Ecosim_mods/InitAllocMod.F90`
**Last verified:** 2026-10-15
---

# APIs Subsystem

## What it is

EcoSIM keeps its model state in grid-indexed module arrays (`../data_types/index.md`). The plant, microbial and solute kernels do not work on those arrays directly; an API layer copies what each kernel needs into per-column or per-layer containers, calls the kernel, and copies results back.

- `f90src/APIs/` is the call surface: drivers (`PlantMod`), ordered send and receive routines (`PlantAPI` and six transfer modules), reduced variants (`PlantCanAPI`, `PlantAPI4Uptake`), and per-layer wrappers for the microbial and solute kernels (`MicBGCAPI`, `GeochemAPI`). Details: `api_layer.md`.
- `f90src/APIData/` defines the twelve plant containers (`plt_site`, `plt_photo`, `plt_rad`, `plt_morph`, `plt_pheno`, `plt_soilchem`, `plt_allom`, `plt_biom`, `plt_ew`, `plt_distb`, `plt_bgcr`, `plt_rbgc`), one domain module each, plus shared dimension pointers and a compatibility facade. Details: `api_data.md`.

```
 Ecosim_datatype grid arrays            APIs                       kernels
 (..., NY, NX), shared by all    ---- PlantAPISend ---->   APIData plt_* containers  <->  f90src/Plant_bgc/
                                 <--- PlantAPIRecv -----   (one column, PFT-first)
                                 ---- MicAPISend ------>   micfor / micstt / micflx  <->  SoilBGCOneLayer
                                 <--- MicAPIRecv -------   (one soil layer)
                                 ---- GeochemAPISend -->   chemvar / solflx          <->  GeoChemEquilibria
                                 <--- GeochemAPIRecv ---   (one soil layer)
```

## Design rules, as verified at cb243228

1. **Plant kernels work on the containers.** Twenty-three `f90src/Plant_bgc/` modules import `APIData` domain modules (`api_data.md`, "Who uses it"). Only three imports from `f90src/Ecosim_datatype/` remain in `f90src/Plant_bgc/`: `CanopyRadDataType` in `InitVegBGC` (`f90src/Plant_bgc/InitVegBGC.F90:14`), and the scalars `iYearCurrent` and `DazCurrYear` (`f90src/Plant_bgc/LitterFallMod.F90:227`, `f90src/Plant_bgc/PlantDisturbsMod.F90:7`). By contrast `f90src/APIs/` has 238 `use` lines of `Ecosim_datatype` modules.
2. **Copies are hourly.** `PlantAPISend` and `PlantAPIRecv` run once per column per hour inside `PlantModel` (`f90src/APIs/PlantMod.F90:71`, `:97`); `MicAPISend` and `MicAPIRecv` once per soil layer per hour (`f90src/APIs/MicBGCAPI.F90:180-195`).
3. **Traits are one way.** `SendPlantTraits` copies every per-PFT trait in each hour (`f90src/APIs/PlantAPI.F90:83-85`) and has no receive counterpart, so the containers' trait values cannot drift from the grid arrays for more than an hour.
4. **Microbial parameters bypass the layer.** The microbial kernel modules import `NitroPars` and `MicBGCPars` directly (for example `f90src/Microbial_bgc/Box_Micmodel/AerobicBacteriaMod.F90:11`); the microbial API copies state and forcing, not parameters.
5. **The library sits on top.** `APIs` may include every lower layer (`f90src/APIs/CMakeLists.txt:20-40`); `APIData` is a separate library (`f90src/APIData/CMakeLists.txt:1-16`).

## When each entry runs in an hour

| Order | Entry | Called from | Gate |
|---|---|---|---|
| 1 | `PlantCanopyRadsModel` (canopy radiation) | `hour1` (`f90src/Modelforc/Hour1Mod.F90:201`), inside `Run_EcoSIM_one_step` | none |
| 2 | `MicrobeModel` | `drivers/ecosim/EcoSIMAPI.F90:63` | `microbial_model` (`:61`) |
| 3 | `PlantModel` | `drivers/ecosim/EcoSIMAPI.F90:73` | `plant_model .and. .not.ldo_radiation_test` (`:71`) |
| 4 | `soluteModel` | `drivers/ecosim/EcoSIMAPI.F90:82` | `soichem_model` (`:80`) |

`ldo_sp_mode` (prescribed phenology) switches `PlantModel` to the reduced `PlantAPI4Uptake` path and forces microbes and chemistry off (`drivers/ecosim/EcoSIMAPI.F90:307-312`). The ATS-coupled driver calls `PlantCanopyRadsModel` (`f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:296`) and, in prescribed-phenology mode, `PlantModel` (`:343`).

## One hour, one column, step by step

1. `PrepHourlyWeather` sets the hour's weather and radiation (`drivers/ecosim/EcoSIMAPI.F90:518`).
2. `HOUR1` (`drivers/ecosim/EcoSIMAPI.F90:49`) calls `PlantCanopyRadsModel` (`f90src/Modelforc/Hour1Mod.F90:201`): `PlantAPICanMSend` → `CanopyConditionModel` → `PlantAPICanMRecv` (`f90src/APIs/PlantMod.F90:134-138`).
3. `WATSUB` updates water and heat on the grid arrays without an API (`drivers/ecosim/EcoSIMAPI.F90:56`).
4. `MicrobeModel` (`drivers/ecosim/EcoSIMAPI.F90:63`): for each soil layer, `MicAPISend` → `SoilBGCOneLayer` → `MicAPIRecv` (`f90src/APIs/MicBGCAPI.F90:180-195`).
5. `PlantModel` (`drivers/ecosim/EcoSIMAPI.F90:73`): `PlantAPISend` (`f90src/APIs/PlantMod.F90:71`), the plant kernel sequence from `EnterPlantBalance` to `ExitPlantBalance` (`:73-95`), `PlantAPIRecv` (`:97`).
6. `soluteModel` (`drivers/ecosim/EcoSIMAPI.F90:82`): for each layer, `GeochemAPISend` → `GeoChemEquilibria` → `GeochemAPIRecv` (`f90src/APIs/GeochemAPI.F90:134-138`).
7. Transport, erosion and `REDIST` (`drivers/ecosim/EcoSIMAPI.F90:91`, `:110`, `:117`) work on the grid arrays; `REDIST` produces the heterotrophic respiration, evapotranspiration and surface-flux accumulators (`f90src/Balances/RedistMod.F90:173`, `:234`, `:410`).
8. `EndCheckBalances` closes the hourly balance bracket opened in `HOUR1` (`drivers/ecosim/EcoSIMAPI.F90:124`; opened at `f90src/Modelforc/Hour1Mod.F90:151`).
9. `hist_update` reads the grid arrays that the receive routines and `REDIST` wrote (`drivers/ecosim/EcoSIMAPI.F90:526`).

Steps 2, 4, 5 and 6 are the only places where data cross the API boundary; everything else in the hour reads and writes the grid arrays directly. A value computed by a kernel therefore becomes visible to the rest of the model, and to the history tapes, only at the receive call that closes its step.

## Call surface

| Public entry | Defined at | Called from |
|---|---|---|
| `PlantModel(yearIJ,NHW,NHE,NVN,NVS)` | `f90src/APIs/PlantMod.F90:37` | `drivers/ecosim/EcoSIMAPI.F90:73`; `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:343` |
| `PlantCanopyRadsModel(I,J,NY,NX,DepthSurfWatIce)` | `f90src/APIs/PlantMod.F90:127` | `f90src/Modelforc/Hour1Mod.F90:201`; `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:296` |
| `PlantAPISend(yearIJ,NY,NX)`, `PlantAPIRecv(I,J,NY,NX)` | `f90src/APIs/PlantAPI.F90:70`, `:40` | `f90src/APIs/PlantMod.F90:71`, `:97` |
| `PlantAPICanMSend`, `PlantAPICanMRecv` | `f90src/APIs/PlantCanAPI.F90:55`, `:197` | `f90src/APIs/PlantMod.F90:134`, `:138` |
| `PlantUptakeAPISend`, `PlantUPtakeAPIRecv` | `f90src/APIs/PlantAPI4Uptake.F90:55`, `:234` | `f90src/APIs/PlantMod.F90:62`, `:68` |
| `MicrobeModel(I,J,NHW,NHE,NVN,NVS)` | `f90src/APIs/MicBGCAPI.F90:84` | `drivers/ecosim/EcoSIMAPI.F90:63` |
| `MicAPI_Init()`, `MicAPI_cleanup()` | `f90src/APIs/MicBGCAPI.F90:60`, `:72` | `f90src/Main/InitEcoSIM.F90:57`, `f90src/Main/EcoSIMDesctruct.F90:59` |
| `soluteModel(I,J,NHW,NHE,NVN,NVS)` | `f90src/APIs/GeochemAPI.F90:23` | `drivers/ecosim/EcoSIMAPI.F90:82` |
| `InitPlantAPIData()`, `DestructPlantAPIData()` | `f90src/APIData/PlantAPIData.F90:20`, `:76` | `f90src/Ecosim_mods/InitAllocMod.F90:106`, `f90src/Main/EcoSIMDesctruct.F90:79` |

## How parameters and management reach the kernels

| Input | Path through this subsystem | Citation |
|---|---|---|
| plant traits (52 calibration names on the plant file) | grid `*_pft` arrays → `SendPlantTraits` → `plt_photo`, `plt_morph`, `plt_pheno`, `plt_allom`, `plt_rbgc` every hour | `f90src/APIs/PlantTraitsTransferMod.F90:50-204` |
| traits derived in STARTQ (e.g. `RootSingleVesselRstaxial_pft` from ARSRA and RVSR) | sent like any trait; only the derived value is sent | `f90src/APIs/PlantTraitsTransferMod.F90:112` |
| plant management for day `I` (cut type, cut height, thinning, harvest fractions) | `SendPlantState` → `plt_distb` | `f90src/APIs/PlantStateTransferMod.F90:313`, `:366-370` |
| management written back by the kernels | `ReceivePlantState` copies the day's schedule back only when the kernel's `iHarvstType_pft` is positive | `f90src/APIs/PlantStateTransferMod.F90:251-257` |
| fertiliser on day `I1 = I+1` (wrapped at year end, `f90src/APIs/PlantColumnTransferMod.F90:171`) | `SendPlantColumnState` → `plt_distb%FERT`; kernel changes returned by `ReceivePlantColumns` | `f90src/APIs/PlantColumnTransferMod.F90:342`, `:88-89` |
| microbial parameters (8 calibration names on the microbial file) | not through the API; kernels import `NitroPars` and `MicBGCPars` | `f90src/Microbial_bgc/Box_Micmodel/AerobicBacteriaMod.F90:11` |

## How calibration targets come back

Each history target's source variable is written by a receive routine before `hist_update` reads it (`../io_and_forcing/history_and_restart.md` §3).

| Target | Grid variable | Written back by |
|---|---|---|
| `ECO_GPP_col` | `Eco_GPP_CumYr_col` | `ReceivePlantState`, accumulated from `plt_bgcr%GrossCO2Fix_pft` (`f90src/APIs/PlantStateTransferMod.F90:58`) |
| `ECO_RA_col` | `Eco_AutoR_CumYr_col` | `ReceivePlantColumns` (`f90src/APIs/PlantColumnTransferMod.F90:64`) |
| `CAN_GPP_pft` | `GrossCO2Fix_pft` | `ReceivePlantState` (`f90src/APIs/PlantStateTransferMod.F90:123`) |
| `NPP_pft` | `NetPrimProduct_pft` | `ReceivePlantState` (`f90src/APIs/PlantStateTransferMod.F90:243`) |
| `SHOOT_C_pft`, `Plant_C_pft` | `ShootElms_pft` | `ReceivePlantState` (`f90src/APIs/PlantStateTransferMod.F90:84`) |
| `Root_C_pft`, `Plant_C_pft` | `RootElms_pft` | `ReceivePlantState` (`f90src/APIs/PlantStateTransferMod.F90:67`) |
| `LEAF_C_pft` | `LeafStrutElms_pft` | `ReceivePlantState` (`f90src/APIs/PlantStateTransferMod.F90:85`) |
| `LAI_xstk_pft` | `CanopyLeafArea_pft` | `ReceivePlantState` (`f90src/APIs/PlantStateTransferMod.F90:94`) |
| `ECO_RH_col`, `ECO_ET_col`, `CO2_SEMIS_FLX_col` | `Eco_HR_CumYr_col`, `QEvap_CumYr_col`, `SurfGasEmiss_all_flx_col` | not through this layer: `RedistMod` (`f90src/Balances/RedistMod.F90:234`, `:410`, `:173`) |

## Per-layer containers of the microbial and solute APIs

The microbial and solute wrappers do not use `APIData`; their containers are defined next to the kernels and passed as arguments.

| Container | Type defined at | Instance | Filled by / returned by |
|---|---|---|---|
| microbial forcing | `micforctype`, `f90src/Microbial_bgc/Box_Micmodel/MicForcTypeMod.F90:13` | `micfor` (`f90src/APIs/MicBGCAPI.F90:45`) | `MicAPISend` (`:198`); layer index and PAR set in `MicBGC1Layer` (`:187`) |
| microbial state | `micsttype`, `f90src/Microbial_bgc/Box_Micmodel/MicStateTraitTypeMod.F90:13` | `micstt` (`f90src/APIs/MicBGCAPI.F90:46`) | `MicAPISend` / `MicAPIRecv` (`:491`) |
| microbial fluxes | `micfluxtype`, `f90src/Microbial_bgc/Box_Micmodel/MicFluxTypeMod.F90:14` | `micflx` (`f90src/APIs/MicBGCAPI.F90:47`) | `MicAPIRecv` |
| microbial diagnostics | `Microbe_Diag_type`, `f90src/Microbial_bgc/Box_Micmodel/MicrobeDiagTypes.F90:277`; `Cumlate_Flux_Diag_type` (`:15`) | `nmicdiag` (`f90src/APIs/MicBGCAPI.F90:48`); `naqfdiag` local to `MicBGC1Layer` | `MicAPIRecv` |
| solute state | `chem_var_type`, `f90src/Geochem/Box_chem/SoluteChemDataType.F90:239` | `chemvar`, local to `soluteModel` (`f90src/APIs/GeochemAPI.F90:37`) | `GeochemAPISend` (`:154`) |
| solute fluxes | `solute_flx_type`, `f90src/Geochem/Box_chem/SoluteChemDataType.F90:138` | `solflx`, local (`f90src/APIs/GeochemAPI.F90:36`) | `GeochemAPIRecv` (`:260`) |

The microbial containers are module-level and allocated once by `MicAPI_Init` (`f90src/APIs/MicBGCAPI.F90:64-66`); the solute ones are local variables of `soluteModel`, whose `chemvar` fields are set to zero at the start of every call (from `f90src/APIs/GeochemAPI.F90:40`).

## Checking that the kernel sees the value in the file

For a plant trait, four places decide what the kernel receives; check them in this order:

1. **Is the name read on the live path?** Find it in `ReadPlantTraitTable` (`f90src/IOutils/PlantInfoMod.F90:1708-1849`). A name present only in `ReadPlantTraitsNC` (`:540-694`) is never read. The reader map at the end of `../io_and_forcing/input_readers.md` lists all 60 calibration names.
2. **Which row is used?** The record is chosen by the PFT key, the first four characters of `pft_type` in `pft_mgmt_in` plus the grid's Koppen zone (`f90src/IOutils/PlantInfoMod.F90:1601-1604`, `:711`).
3. **Is it rescaled or replaced?** See the `ReadPlantProperties` rescaling (`f90src/IOutils/PlantInfoMod.F90:507-533`) and any STARTQ derivation (`f90src/Ecosim_mods/StartqMod.F90`).
4. **Is it sent?** Find the grid array in `SendPlantTraits` (`f90src/APIs/PlantTraitsTransferMod.F90:50-204`); if only a derived array appears there, the parameter acts through that derivation.

With `disp_planttrait = .true.` in the runfile, `readq` opens `<case>.plant_trait.desc.<year>` (`f90src/IOutils/PlantInfoMod.F90:83-87`) and `SetPlantTraits` writes each PFT's copied values into it, before the step-3 rescaling, in years when the PFT set changed (`:855-866`).

## Things that are easy to get wrong

- **Editing a container value inside a kernel does not persist** unless a receive routine copies that component back. Traits never come back.
- **`MaxSoilLays4Root_pft` differs by path.** In prescribed-phenology mode it is set to `NK_col` on every send (`f90src/APIs/PlantAPI4Uptake.F90:148`); in the full model it is the state updated by phenology and root growth and copied in by `SendPlantState` (`f90src/APIs/PlantStateTransferMod.F90:391`).
- **Unfilled components hold `1.0e30`.** Containers are initialised with `spval` (`f90src/Utils/data_const_mod.F90:62`), unlike the zero-filled grid arrays.
- **`plt_rbgc` is never destroyed** at shutdown (`f90src/APIData/PlantAPIData.F90:76-101`); harmless at process exit, but a leak for any driver that re-initialises.

## Changes since 2dea74d9

| Item | 2dea74d9 | cb243228 |
|---|---|---|
| `PlantAPI.F90` | 1527 lines, all copies inline | 104-line dispatcher plus six transfer modules (`api_layer.md` §3) |
| `PlantAPIData.F90` | 2179 lines, twelve types | 104-line facade plus twelve domain modules and `PlantAPICommonData` (`api_data.md`) |
| plant kernel imports | `use PlantAPIData` | domain modules |
| `MicrobeModel` | per-layer send, kernel, receive | adds PAR attenuation for cyanobacteria (`f90src/APIs/MicBGCAPI.F90:84-176`) |
| `PlantModel` | no seed deposition | `SeedDeposition` at hour 1 (`f90src/APIs/PlantMod.F90:75-79`) |
| callers of `MicrobeModel`, `soluteModel` | called from `drivers/ecosim/EcoSIMAPI.F90` (the old wiki said "no caller") | called from `drivers/ecosim/EcoSIMAPI.F90:63`, `:82` |

## Navigation

| Page | Covers |
|---|---|
| [`api_layer.md`](api_layer.md) | every file in `f90src/APIs/`: call order, transfer modules, trait flow, microbial and solute wrappers |
| [`api_data.md`](api_data.md) | every file in `f90src/APIData/`: types, singletons, lifecycle, component inventory, adding a plant parameter |
| [`../data_types/index.md`](../data_types/index.md) | the grid-array layer on the other side of the copies |
| [`../io_and_forcing/history_and_restart.md`](../io_and_forcing/history_and_restart.md) | how the returned values reach the history tapes |
