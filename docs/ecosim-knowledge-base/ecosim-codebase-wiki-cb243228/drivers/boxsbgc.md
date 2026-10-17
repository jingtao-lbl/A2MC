---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `drivers/boxsbgc/` (`batchsbgc.F90`, `batchmod.F90`, `ChemMod.F90`, `ForcTypeMod.F90`, `MicIDMod.F90`), `drivers/boxshared/ChemIDMod.F90`
**Last verified:** 2026-10-15
---

# Soil BGC Batch Driver (`boxsbgc.x`)

`boxsbgc.x` runs the single-layer soil microbial model (`SoilBGCOneLayer`), the no-salt geochemistry and the gas-exchange fluxes on one box, driven by a NetCDF forcing file. It is meant for exercising the microbial code without the soil-water, transport and plant physics. Two facts limit what it can show at cb243228. Temperature and moisture are fixed every step whatever the forcing says (section 4). The forcing reader also requires two dimensions that the model's own forcing writer does not define (section 3).

## 1. Files

| File | Lines | Contents |
|---|---|---|
| `drivers/boxsbgc/batchsbgc.F90` | 240 | `program main` (`:1-33`), `usage` (`:37-44`), `RunModel` (`:47-240`) |
| `drivers/boxsbgc/batchmod.F90` | 1764 | `getvarllen` (`:31-41`), `initmodel` (`:43-90`), `BatchModelConfig` (`:94-303`), `Initboxbgc` (`:308-502`), `UpdateStateVars` (`:504-653`), `getvarlist` (`:657-1239`), `RunMicBGC` (`:1241-1278`), `CalcSurflux` (`:1280-1669`), `UpdateSOMORGM` (`:1672-1762`) |
| `drivers/boxsbgc/ChemMod.F90` | 272 | `RunModel_nosalt` (`:13-40`), `RetrieveYstatef` (`:45-189`), `SetChemVar` (`:191-270`) |
| `drivers/boxsbgc/ForcTypeMod.F90` | 503 | `forc_type` container, `ReadFORC` (`:216-335`), `UpdateFORC` (`:338-501`) |
| `drivers/boxsbgc/MicIDMod.F90` | 109 | microbial `cid_*` / `fid_*` index declarations |
| `drivers/boxshared/ChemIDMod.F90` | 392 | chemistry index declarations shared with `aquachem` |

Build: `drivers/boxsbgc/CMakeLists.txt` globs `*.F90` into `boxsbgc.x` and adds include paths for `f90src/Geochem/Box_chem`, `f90src/Microbial_bgc/Box_Micmodel` and `drivers/boxshared`.

`batchmod.F90` and `ForcTypeMod.F90` changed between 2dea74d9 and cb243228. The single microbial functional-group count `NumMicbFunGrupsPerCmplx` was split into a heterotroph count `NumMicbHFunGrupsPerCmplx` and an autotroph count `NumMicbAFunGrupsPerCmplx` (compile-time 8 and 6, `f90src/Modelconfig/EcoSIMConfig.F90:24-25`).

## 2. Command line and run flow

`boxsbgc.x <namelist file>`; a wrong argument count calls `usage` and `endrun` (`drivers/boxsbgc/batchsbgc.F90:17-22`). The file goes through the 4096-byte `namelist_to_buffer` (`:29`).

`RunModel` (`:47-240`):

| Step | Action | Citation |
|---|---|---|
| 1 | Read `/driver_nml/` (section 3); a read error calls `endrun` | `:107-108`, `:129-136` |
| 2 | Fix the solver sub-steps: `NPH = 1`, `NPT = 15`, `NPG = NPT*NPH`, `dts_gas = 1/NPG`, `dts_HeatWatTP = 1/NPH`, `dt_GasCyc = 1/NPT` | `:147` |
| 3 | `nvars = getvarllen()` (also runs `micpar%Init()` and `micpar%SetPars()`), then `getvarlist` | `:152-155`; `drivers/boxsbgc/batchmod.F90:31-41` |
| 4 | Allocate and zero the state vectors | `drivers/boxsbgc/batchsbgc.F90:159-161` |
| 5 | Copy the atmospheric mixing ratios and `disvolonly` into `forc`; `ReadFORC(forc, forc_file)` | `:164-173` |
| 6 | `micfor%Init()`, `micstt%Init()`, `micflx%Init()` | `:175-177` |
| 7 | `initmodel`, which calls `initNitro1Layer` (`drivers/boxsbgc/batchmod.F90:54`), the same initialiser the full model reaches through `InitModules -> initNitro` (`f90src/Main/InitEcoSIM.F90:45`; `f90src/Microbial_bgc/Layers_Micmodel/SoilBGCNLayMod.F90:45-51`) | `drivers/boxsbgc/batchsbgc.F90:180` |
| 8 | `timer%Init(namelist_buffer=...)`; history `boxsbgc.<case_id>.<model_name>` | `:188-198` |
| 9 | Loop: `update_time_stamp`; `UpdateFORC(forc, forctype)`; `BatchModelConfig`; `RunMicBGC`; `update_time_stamp` again; copy state, carry `forc%ORGC = micfor%ORGC`; `hist_wrap`; exit at `its_time_to_exit` | `:201-232` |
| 10 | History restart write; destroy the microbial objects | `:233-239` |

The clock is advanced twice per iteration (`:203`, `:217`). With the default `delta_time = 1800` s each model step therefore spans one hour of clock time, while history samples are taken after the second advance.

`RunMicBGC` (`drivers/boxsbgc/batchmod.F90:1241-1278`): unless `forc%disvolonly`, call `SoilBGCOneLayer(I=1, J=1, micfor, micstt, micflx, ...)` and then `RunModel_nosalt` (geochemistry, `ChemMod.F90:13-40`). Then always `CalcSurflux` (gas dissolution, volatilisation and atmosphere exchange, `:1280-1669`), `UpdateStateVars` and `UpdateSOMORGM` (`:1272-1276`).

## 3. Namelists and the forcing file

`/driver_nml/` (`drivers/boxsbgc/batchsbgc.F90:107-108`, defaults `:113-127`):

| Member | Default | Meaning |
|---|---|---|
| `model_name` | `'boxsbgc'` | history label |
| `case_id` | `'exp0'` | history label |
| `hist_freq` | `'day'` | history frequency |
| `salton` | `.false.` | read, but this driver always calls the no-salt solver |
| `forc_file` | `'bbforc.nc'` | forcing file |
| `CO2E`, `OXYE`, `Z2OE`, `Z2GE`, `ZNH3E`, `CH4E`, `H2GE` | 370, 2.1e5, 0.3, 7.8e5, 0.005, 1.8, 1e-3 ppmv | atmospheric mixing ratios |
| `forctype` | `0` | which derived forcing terms are recomputed each step (section 4) |
| `disvolonly` | `.false.` | skip the microbial and chemistry calls; run only gas dissolution and volatilisation |

`/ecosim_time/` is read by the timer as in every driver (`f90src/Utils/ecosim_time_mod.F90:240-267`).

`ReadFORC` (`drivers/boxsbgc/ForcTypeMod.F90:216-335`) opens `forc_file` and reads dimensions with `get_dim_len`, which calls `endrun` for a missing dimension (`f90src/Utils/ncdio_pio.F90:1841-1844`). It requires `jcplx`, `jsken`, `NumHetetr1MicCmplx`, `NumMicrobAutoTrophCmplx`, `NumLiveHeterBioms`, `NumLiveAutoBioms`, `element`, `nlbiomcp`, `ndbiomcp`, and, new at cb243228, `NumMicbAFunGrupsPerCmplx` and `NumMicbHFunGrupsPerCmplx` (`drivers/boxsbgc/ForcTypeMod.F90:229-239`). The full model's own forcing writer (`/bbgcforc/` with `do_bgcforc_write`) defines the first nine dimensions but neither of the two new ones (`f90src/IOutils/ForcWriterMod.F90:53-62`). A `bbforc.nc` written by the model at cb243228 therefore stops `boxsbgc.x` in `ReadFORC`. The values read for the two new dimensions are not used afterwards; the driver uses the compile-time counts in `micpar`.

The variables `ReadFORC` reads include solution N and P (`ZNH4S`, `ZNO3S`, `ZNO2S`, `H2PO4`, `H1PO4`), `pH`, pore and soil volumes and mass, `ORGC`, porosity, field capacity and wilting point, the soil chemistry inputs (`CEC`, `AEC`, `CFE`, `CCA`, ..., `CALPO`, `CFEPO`, `CCAPD`, `CCAPH`), the microbial and organic-matter pools (`mBiomeHeter`, `mBiomeAutor`, `OSM`, `OSA`, `ORM`, `OHM`, `DOM`), the water-retention constants and `ATKA` (`:250-334`).

Variables `ReadFORC` reads, grouped (names verbatim, `drivers/boxsbgc/ForcTypeMod.F90:250-334`):

| Group | Variables |
|---|---|
| Mineral N and P in solution | `ZNH4S`, `ZNO3S`, `ZNO2S`, `H2PO4`, `H1PO4` |
| Soil-organic stoichiometry | `CNOSC`, `CPOSC` |
| Acidity | `pH` |
| Geometry and mass | `VLSoilPoreMicP`, `VLSoilMicP`, `BKVL`, `BKDS`, `DLYR3`, `POROS` |
| Water retention | `FC`, `WP`, `SRP`, `THETY`, `PSIMX`, `PSIMD`, `PSIMS`, `PSISD`, `PSISE` |
| Organic matter and microbes | `ORGC`, `ElmAllocmatMicrblitr2POM`, `EHUM`, `EPOC`, `mBiomeHeter`, `mBiomeAutor`, `OSM`, `OSA`, `ORM`, `OHM`, `DOM` |
| Exchange capacities and cations | `CEC`, `AEC`, `CFE`, `CCA`, `CMG`, `CNA`, `CKA`, `CSO4`, `CCL`, `ZMG`, `ZNA`, `ZKA`, `CAL` |
| Initial minerals | `CALPO`, `CFEPO`, `CCAPD`, `CCAPH`, `CALOH`, `CFEOH`, `CCACO`, `CCASO` |
| Temperature | `ATCS`, `ATKA` (`TKS` is then overwritten each step, section 4) |

Every read is a bare `ncd_getvar`, so a missing variable also ends the run in `endrun` (`f90src/Utils/ncdio_pio.F90:463-466`).

## 4. Temperature and moisture are fixed

`UpdateFORC` starts by assigning `TKS = 298 K` and `THETW = 0.65` (relative saturation) on every call (`drivers/boxsbgc/ForcTypeMod.F90:381-382`). These are aliases for `forc%TKS` and `forc%THETW` (`:377-378`), which `BatchModelConfig` passes straight to the microbial model (`drivers/boxsbgc/batchmod.F90:147-148`). `forctype` only controls whether the quantities derived from them are recomputed after the first step:

| Block | Recomputed when | What it computes | Citation |
|---|---|---|---|
| water | first step, or `forctype <= 1` | matric potential from `THETW`, film thickness, tortuosity, air-filled porosity, water and air volumes | `:383-402` |
| temperature | first step, or `forctype` 0 or 2 | gas solubilities at `TKS`, atmospheric gas concentrations | `:404-435` |
| transport | first step, or `forctype <= 2` | effective solute diffusivity, gas diffusivities scaled by `TEFGASDIF(TKS)`, gas boundary-layer conductances | `:436-468` and following |

The comment "0: (transient), 1: T const, 2: water const, 3: T and water const" (`:341`) describes the intent. Since `TKS` and `THETW` are constants, every `forctype` yields the same 298 K, 0.65-saturation box. The microbial temperature response is not exercised.

## 5. State vector and history

`Initboxbgc` (`drivers/boxsbgc/batchmod.F90:308-502`) numbers the gas, solute, organic-matter (`oqc`, `oqn`, `oqp`, `oqa`, `ohc`, ..., `orp` slices) and microbial biomass (`mBiomeHeter`, `mBiomeAutor`) states, and the diagnostic fluxes, with `addone`. `_b` and `_e` suffixes mark the inclusive start and end of each multi-species slice. `getvarlist` (`:657-1239`) assigns the history names. Two of its loops pair the autotroph group count with heterotroph index ranges, or the reverse: `DO N=1,NumMicbAFunGrupsPerCmplx; DO NGL=JGniH(N),JGnfH(N)` for the autotroph biomass names (`:956-957`), and `DO N=1,NumMicbAFunGrupsPerCmplx; DO NGL=JGniA(N),JGnfA(N)` for the heterotroph `RNH4DmndSoilHeter` names (`:1112-1113`). The labels in those slices may not match the quantities stored.

`BatchModelConfig` (`:94-303`) unpacks `ystates0l` and `forc` into `micfor`, `micstt` and `micflx`. `UpdateStateVars` (`:504-653`) packs the results back. When a microbial state variable is added to the library, both routines and `Initboxbgc` need the new slot.

## 6. Gas exchange (`CalcSurflux`)

`CalcSurflux` (`drivers/boxsbgc/batchmod.F90:1280-1669`) handles the fluxes the column model would get from transport. Its header comment says it computes exchange with the atmosphere, dissolution and volatilisation between the gaseous and dissolved phases in the soil, and dissolution and volatilisation against the atmosphere, with no micropore-macropore exchange (`:1282-1286`). It runs a gaseous atmosphere-soil exchange when air-filled pore volume is positive (`:1394`, `:1430`). Dissolution and volatilisation against the atmosphere are computed as the difference between the dissolved concentration and the atmospheric equilibrium concentration, times a dissolution rate (`:1457-1460`), and are accumulated (`:1514`). Gas-aqueous partitioning within the soil follows, including the NH3 band and non-band zones (`:1533-1577`). With `disvolonly = .true.` this is the only physics that runs.

## 7. Geochemistry inside the box (`ChemMod.F90`)

`RunModel_nosalt` fills `chemvar` with `SetChemVar` (`drivers/boxsbgc/ChemMod.F90:191-270`; pH from the forcing file, `chemvar%PH = forc%pH`, `:225`), calls `NoSaltChemEquilibria(0,0,0,0,0, ...)` (`:36`) and adds the fluxes with `RetrieveYstatef` (`:45-189`). The P precipitate and sorption states start from the forcing file and `initmodel`, not from the full model's `STARTE`. The same rule applies here as in the full model: if the surface-site states (`X-OH`, `X-OH2+`) are zero, phosphate sorption fluxes are zero (`../geochem/equilibria_and_sorption.md` §3).

## 8. A minimal runfile

```
&driver_nml
  model_name = 'boxsbgc'
  case_id    = 'test1'
  hist_freq  = 'day'
  forc_file  = 'bbforc.nc'
  forctype   = 3
  disvolonly = .false.
/
&ecosim_time
  delta_time  = 1800.
  stop_n      = 1
  stop_option = 'nyears'
  rest_opt    = 'never'
/
```

`delta_time = 1800.` with the two clock advances per step (section 2) gives one model step per clock hour. `forctype = 3` makes explicit that temperature and water are constant, which they are for any value (section 4). The forcing file must contain the dimensions and variables in section 3.

## 9. Fixed solver sub-steps

| Variable | Value in `boxsbgc` | Meaning | Citation |
|---|---|---|---|
| `NPH` | 1 | heat and water sub-cycles per hour | `drivers/boxsbgc/batchsbgc.F90:147` |
| `NPT` | 15 | gas sub-cycles per `NPH` | `:147` |
| `NPG` | 15 | total gas sub-cycles per hour (`NPT*NPH`) | `:147` |
| `dts_gas`, `dts_HeatWatTP`, `dt_GasCyc` | 1/15, 1, 1/15 | fractional step lengths | `:147` |

The full model sets these through `set_ecosim_solver` from `NPXS` and `NPYS` (`f90src/Ecosim_mods/StartsMod.F90:952-982`). `boxsbgc` hard-codes them, so its gas exchange is not sub-cycled like the column model's.

## 10. What `boxsbgc.x` is good for

- Checking that a change to the microbial library still runs and conserves mass at fixed 298 K and 0.65 saturation.
- Comparing guild configurations with `/Microbes/`-style counts fixed at compile time.
- Not for temperature or moisture sensitivity, unless `UpdateFORC` is edited first.
- Not with forcing files written by the model at cb243228, unless the two group-count dimensions are added to the file.

## Cross-references

- Geochemistry called here: `../geochem/`.
- `/ecosim_time/` and how drivers end: `ecosim_main.md` §3 and §6.
- Template the driver follows: `standalone_drivers.md`.
