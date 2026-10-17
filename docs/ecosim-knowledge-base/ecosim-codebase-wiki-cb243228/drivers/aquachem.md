---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `drivers/aquachem/` (`aquachem.F90`, `AquachemMod.F90`, `AquaSaltChemMod.F90`), `drivers/boxshared/ChemIDMod.F90`
**Last verified:** 2026-10-15
---

# Aquachem Batch Driver (`aquachem.x`)

`aquachem.x` runs EcoSIM's aqueous equilibrium solver on a single virtual box. There is no grid, no climate, no transport, no plants and no microbes. Each step it packs a flat state vector into the solver's `chem_var_type`, calls either `NoSaltChemEquilibria` (`f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:22`) or `SaltChemEquilibria` (`f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90:299`), and adds the returned fluxes back to the state. It is a quick way to see how the solver relaxes a fixed initial condition. It does not reproduce a soil column, and at cb243228 its salt mode is not usable (section 5).

None of these files changed between 2dea74d9 and cb243228.

## 1. Files

| File | Lines | Contents |
|---|---|---|
| `drivers/aquachem/aquachem.F90` | 173 | `program main` (`:1-29`), `usage` (`:34-41`), `RunModel` (`:46-173`) |
| `drivers/aquachem/AquachemMod.F90` | 443 | `getvarllen` (`:19-29`), `Init_geochem_nosalt` (`:34-100`), `getvarlist` (`:104-122`), `initmodel` (`:125-140`), `initmodel_nosalt` (`:145-190`), `Runchem` (`:193-211`), `RunModel_nosalt` (`:214-237`), `SetChemVar` (`:240-316`), `RetrieveYstatef` (`:320-441`) |
| `drivers/aquachem/AquaSaltChemMod.F90` | 1003 | `RunModel_salt` (`:19-43`), `initmodel_salt` (`:47-55`), `Init_geochem_salt` (`:57-259`), `getvarlist_salt` (`:263-851`), private `SetChemVar` (`:854-877`), private `RetrieveYstatef` (`:880-1001`) |
| `drivers/boxshared/ChemIDMod.F90` | 392 | The `cid_*` (state) and `fid_*` (flux) index variables shared with `boxsbgc` |

Build: `drivers/aquachem/CMakeLists.txt` globs `*.F90` into `aquachem.x` (`file(GLOB AQUACHEM_DRIVER_SOURCES "*.F90")`, then `add_ecosim_executable(aquachem.x ...)`). Both modules declare `private` and export only their listed routines, so the two `SetChemVar` routines do not clash.

## 2. Command line and run flow

`aquachem.x <namelist file>`. Any other argument count prints `usage` and calls `endrun` (`drivers/aquachem/aquachem.F90:13-18`), which exits 0 (see `ecosim_main.md` §6). The file is read with the same 4096-byte `namelist_to_buffer` as the full model (`:25`).

`RunModel(namelist_buffer)` (`:46-173`):

| Step | Action | Citation |
|---|---|---|
| 1 | Read `/driver_nml/` (`model_name`, `case_id`, `hist_freq`, `salton`); a read error calls `endrun` | `:81`, `:84-95` |
| 2 | `nvars = getvarllen(salton)`; allocate the history name, unit and type lists; `getvarlist` | `:107-110` |
| 3 | Allocate `ystatesf(1,nvars)`, `ystates0l`, `ystatesfl`, all zero | `:115-117` |
| 4 | `initmodel(nvars, ystates0l, salton, err_status)` | `:120-124` |
| 5 | `timer%Init(namelist_buffer=...)`; `dtime = timer%get_step_size()` | `:128-129` |
| 6 | History name `aquachem.nosalt.<case_id>.<model_name>` or `aquachem.salt...`; `hist%init` | `:132-142` |
| 7 | Loop: `update_time_stamp`; `Runchem`; copy `ystatesfl` into `ystates0l` and the history row; `hist_wrap`; print the year; exit when `its_time_to_exit` | `:144-168` |
| 8 | Write a history restart `histrst('aquachem.x','write', ...)` | `:169-171` |

The state persists from one step to the next (`ystates0l = ystatesfl`, `:159`). Each step therefore applies the solver's hourly relaxation rates once more to the evolving box. The solver's rate constants are per hour (`f90src/Modelpars/SoluteParMod.F90:143-152`) and do not see `dtime`.

## 3. Namelists

| Group | Members and defaults | Citation |
|---|---|---|
| `/driver_nml/` | `model_name = 'mock'`, `case_id = 'exp0'`, `hist_freq = 'day'`, `salton = .false.` | `drivers/aquachem/aquachem.F90:81`, `:84-87` |
| `/ecosim_time/` | `delta_time = 1800` s, `stop_n = 2`, `stop_option = 'nyears'` (`nsteps`, `ndays`, `nmonths`, `nyears`), `rest_frq`, `rest_opt = 'never'`, `diag_frq`, `diag_opt`; read only if the text `ecosim_time` appears in the buffer | `f90src/Utils/ecosim_time_mod.F90:240-256`, `:261-267` |

The timer group is `&ecosim_time`. A group written as `&ecosim_time_nml` passes the substring test but fails the read, and the run ends in `endrun` (`f90src/Utils/ecosim_time_mod.F90:263-265`). With no `/ecosim_time/` group the harness runs two years of 1800 s steps.

## 4. No-salt mode (`salton = .false.`)

### 4.1 State vector

`Init_geochem_nosalt` assigns `cid_*` and `fid_*` indices with `addone` in declaration order (`drivers/aquachem/AquachemMod.F90:34-100`). The states are solution NH4, NH3, HPO4 and H2PO4 in band and non-band zones, exchangeable NH4 (band and non-band), the surface sites `X-OH`, `X-OH2+` and sorbed `X-HPO4`, `X-H2PO4` (band and non-band), and the five P precipitates in each zone. The fluxes are the solver's `TRChem_*` outputs.

The 28 state slots, in the order `Init_geochem_nosalt` assigns them:

| Group | `cid_*` names |
|---|---|
| Solution P | `cid_H1PO4_2e_aque_mole_conc`, `cid_H1PO4_2e_band_mole_conc`, `cid_H2PO4_1e_aque_mole_conc`, `cid_H2PO4_1e_band_mole_conc` |
| Solution N | `cid_NH3_aque_mole_conc`, `cid_NH3_aqu_band_mole_conc`, `cid_NH4_1p_aque_mole_conc`, `cid_NH4_1p_band_mole_conc` |
| Exchangeable NH4 | `cid_XNH4_mole_conc`, `cid_XNH4_band_mole_conc` |
| Surface sites and sorbed P | `cid_XHPO4_band_mole_conc`, `cid_XH2PO4_band_mole_conc`, `cid_XROH_band_mole_conc`, `cid_XHPO4_mole_conc`, `cid_XROH2_band_mole_conc`, `cid_XH2PO4_mole_conc`, `cid_XROH1_mole_conc`, `cid_XROH2_mole_conc` |
| Precipitates (non-band, band) | `cid_Precp_AlPO4_mole_conc` / `cid_PrecpB_AlPO4_mole_conc`, the same for CaHPO4, `Ca5P3O12O3H3` (apatite), CaH4P2O8, FePO4 |

The 29 flux slots are the solver outputs `fid_TRChem_NH4_soil` through `fid_TRChem_CaH4P2O8_precip_band_soil`, plus `fid_TRChem_Al_3p_soil`. The block `fid_TRChem_NH4_soil:fid_TRChem_Al_3p_soil` is zeroed at initialisation (`drivers/aquachem/AquachemMod.F90:155`). There is no `X-O-` slot: the no-salt solver has no surface protonation step.

### 4.2 Initial condition (`initmodel_nosalt`, `:145-190`)

| Quantity | Initial value | Citation |
|---|---|---|
| HPO4, H2PO4 (non-band and band) | 7.6e-3, 0.56 mol m-3 | `:159-162` |
| NH3 (non-band, band) | 1.39e-4, 1.95e-4 | `:163-164` |
| NH4 (non-band, band) | 1.21, 372.2 | `:165-166` |
| Exchangeable NH4 (non-band, band) | 0.32, 0.32 | `:167-168` |
| Surface sites `X-OH`, `X-OH2+` and sorbed `X-HPO4`, `X-H2PO4`, all zones | **0** | `:170-177` |
| AlPO4 (non-band, band) | 0.623, 0.623 | `:179-180` |
| Ca(H2PO4)2 band | 600.89 | `:186` |
| other precipitates | 0 | `:181-188` |

Because every surface-site pool starts at zero and no reaction creates sites, the phosphate ligand-exchange fluxes are identically zero for the whole harness run (`f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:393-405`). The harness exercises precipitation, dissolution, H2PO4 dissociation and NH4 exchange, but not P sorption. The full model on a fresh run is in the same position (`../geochem/index.md` §5).

### 4.3 Fixed inputs every step (`SetChemVar`, `:240-316`)

| Input | Value | Citation |
|---|---|---|
| Gapon coefficients `GKCA`, `GKCH`, `GKCM`, `GKCK`, `GKCN`, `GKC4` | 0.25, 0.25, 0.60, 3.0, 0.16, 2.5e-2 | `:249-261` |
| Soil mass, water volumes (total, P non-band, P band, NH4 non-band, NH4 band) | 4.08e-2; 1.54e-2, 1.53e-2, 5.06e-5, 1.51e-2, 3.16e-4 | `:263-269` |
| CEC, AEC | 0.724, 0.116 | `:270`, `:278` |
| pH | 5.33 | `:271` |
| Band volume fractions (NH4) | 0.98 non-band, 0.02 band | `:272-273` |
| Al, Fe, Ca caps (`CAL`, `CFE`, `CCA`) | 37.04, 0, 2.5 | `:275-277` |
| Mg, Na, K | 0 | `:280-282` |
| Dissolved CO2 | 2.31e-2 | `:283` |

The pH is fixed. As in the full model, the no-salt solver takes [H+] from it and does not compute pH (`f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:278`).

### 4.4 One step (`RunModel_nosalt`, `:214-237`)

`SetChemVar` -> `NoSaltChemEquilibria(0,0,0,0,0,chemvar,solflx)` (`:233`) -> `RetrieveYstatef`. The five leading zeros are the `I, J, L, NY, NX` arguments, which the executable body of `NoSaltChemEquilibria` never references (`f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:37-775`). `RetrieveYstatef` adds each net flux divided by the relevant water volume (`:320-441`). Two retrieval inconsistencies (code reading): band NH4 is incremented with the band NH3 flux `TRChem_NH3_band_soil` (`:343`), and the sorbed-NH4 increment is divided by a water volume (`:339`), while the solver treats sorbed NH4 per unit soil mass (`f90src/Geochem/Layers_chem/SoluteMod.F90:369`).

## 5. Salt mode (`salton = .true.`): not usable at cb243228

`getvarllen(.true.)` registers the extended salt index set through `Init_geochem_salt` (`drivers/aquachem/AquaSaltChemMod.F90:57-259`). The run path is `RunModel_salt`: `SetChemVar` -> `SaltChemEquilibria` -> `RetrieveYstatef` (`:19-43`). However:

- `initmodel_salt` has an empty body (`:47-55`). It does not even reset `err_status`, which is `intent(out)`, so the `check_status()` that follows in `aquachem.F90:122` reads an undefined status.
- The salt `SetChemVar` sets only the six Gapon coefficients (`:854-877`). Its `chemvar` is `intent(out)`, so pH, CEC, AEC, all water volumes and every concentration reach `SaltChemEquilibria` undefined.

Use the full model with `salt_model = .true.` to exercise the salt solver.

## 6. Shared chemistry IDs (`drivers/boxshared/ChemIDMod.F90`)

`ChemIDMod` declares the integer index variables (`cid_CO2S`, `cid_H1PO4_2e_aque_mole_conc`, `cid_NH4_1p_aque_mole_conc`, ... and the matching `fid_*`) but does not assign them. Each driver's `Init_geochem_*` or `Initboxbgc` routine numbers them at run time with `addone` against a local counter. The value of `cid_X` is the slot of species X in the flat state vector. `aquachem` and `boxsbgc` both link the `boxshared` library, so they share the name space.

## 7. Differences from the full model

| Aspect | `aquachem.x` | Full model (`soluteModel`) |
|---|---|---|
| Geometry | one box, flat vector | per layer `(L, NY, NX)` loop in `soluteModel` (`f90src/APIs/GeochemAPI.F90:95-149`) |
| Inputs that change in time | none; all forcing in `SetChemVar` is constant | plant uptake, microbial release and fertilizer dissolution update the solution before every call (`f90src/Geochem/Layers_chem/SoluteMod.F90:362-450`) |
| pH | 5.33 constant | grid-file `PH`, constant per layer |
| Surface sites | zero by construction | zero on a fresh run because of the STARTE path (`../geochem/index.md` §5) |
| Unit conversion | none; state kept in mol m-3 | mol to g in `UpdateFertilizerBand` (`f90src/Geochem/Layers_chem/SoluteMod.F90:117-132`) |
| Fertilizer bands | band volume fixed by `SetChemVar` | band geometry evolves (`UpdateFertilizerBand`) |
| History | `histf_type` from `bhistMod` | `HistFileMod` tapes |

## 8. A minimal runfile

```
&driver_nml
  model_name = 'nosalt_test'
  case_id    = 'exp0'
  hist_freq  = 'day'
  salton     = .false.
/
&ecosim_time
  delta_time  = 3600.
  stop_n      = 1
  stop_option = 'nyears'
  rest_opt    = 'never'
/
```

Group and member names come from `drivers/aquachem/aquachem.F90:81` and `f90src/Utils/ecosim_time_mod.F90:240-241`. With `delta_time = 3600.` one model step corresponds to one solver call at the solver's hourly rates. The history file is `aquachem.nosalt.exp0.nosalt_test` plus the history module's suffixes (`drivers/aquachem/aquachem.F90:132-142`).

## 9. When to use it

- Checking that an edit to `ChemEquilibriaMod.F90` still conserves P across the dissolution and dissociation terms. Compare the summed P states between steps.
- Seeing how quickly a precipitate relaxes under `TPD = 2.5e-3 h-1` (`f90src/Modelpars/SoluteParMod.F90:144`) from a known supersaturation.
- Not for P-sorption experiments, unless you first give the surface-site states nonzero initial values in `initmodel_nosalt`.
- Not for salt chemistry (section 5).

## Cross-references

- The solver equations: `../geochem/equilibria_and_sorption.md`.
- The geochem call chain in the full model: `../geochem/index.md`.
- Shared batch pattern and `/ecosim_time/`: `standalone_drivers.md`, `ecosim_main.md` §3.
