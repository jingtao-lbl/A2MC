---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/` + `drivers/` (full repo)
**Last verified:** 2026-10-15
---

# EcoSIM Codebase Wiki

This wiki documents the EcoSIM source tree at commit `cb243228`: upstream EcoSIM merged through `09eb674a`, plus two plant mass-balance commits on the `jingtao-lbl/EcoSIM` fork, `9669b817` (the plant balance counts every root layer its fluxes reach) and `cb243228` (a default-off switch, `conserve_root_clamp`, that stops the fibrous-root clamp from creating mass). Every technical claim cites `(path/from/repo/root.F90:NNN)` at this commit, and every page names the enclosing subroutine where it cites a parameter's use.

It replaces the wiki pinned at `2dea74d9`, 323 commits and 282 Fortran files earlier. Each of the 14 sections below was audited against `cb243228` before it was rewritten (Workflow B), and every page was rewritten from the source at this commit; none was carried forward.

## Navigation

| Section | Path | What it covers |
|---|---|---|
| **Overview** | [`overview/`](overview/index.md) | What EcoSIM is, how a run is driven, the subsystem map; [`source_tree.md`](overview/source_tree.md) lists the directories |
| **Reference** | [`reference/`](reference/module_inventory.md) | [`module_inventory.md`](reference/module_inventory.md): every `.F90` file with its status since `2dea74d9`; [`calibration_parameter_source_map.md`](reference/calibration_parameter_source_map.md): every curated parameter's read site and physics use sites; [`curated_output_source_map.md`](reference/curated_output_source_map.md): every output the knowledge graph names, where it is registered and the model variable that fills it; [`curated_mechanism_index.md`](reference/curated_mechanism_index.md): each graph mechanism and the page that documents it. All three are generated from the source and the curated seed |
| **Drivers** | [`drivers/`](drivers/index.md) | The standalone executable and its namelists, the ATS coupling, the batch drivers |
| **Core** | [`core/`](core/index.md) | Orchestration and call order, grid and layer indices, model configuration and namelist switches, utilities |
| **Data types** | [`data_types/`](data_types/index.md) | The `Ecosim_datatype/` state and flux arrays |
| **APIs** | [`apis/`](apis/index.md) | The API layer between the column model and the plant and microbial kernels |
| **Plant BGC** | [`plant_bgc/`](plant_bgc/index.md) | [`photosynthesis_and_respiration.md`](plant_bgc/photosynthesis_and_respiration.md), [`phenology.md`](plant_bgc/phenology.md), [`growth_and_allocation.md`](plant_bgc/growth_and_allocation.md), [`roots_and_uptake.md`](plant_bgc/roots_and_uptake.md) (roots, shoot-root exchange, root hydraulics, nutrient uptake, the plant mass balance) |
| **Microbial BGC** | [`microbial_bgc/`](microbial_bgc/index.md) | [`decomposition_and_som.md`](microbial_bgc/decomposition_and_som.md) and [`soil_plant_nutrient_coupling.md`](microbial_bgc/soil_plant_nutrient_coupling.md), the path from mineralization to plant uptake |
| **Geochem** | [`geochem/`](geochem/index.md) | Solute equilibria, prescribed pH, phosphorus sorption |
| **HydroTherm** | [`hydrotherm/`](hydrotherm/index.md) | Soil water and heat, surface energy balance, snow, canopy interception, evapotranspiration |
| **Transport** | [`transport/`](transport/index.md) | Gas and solute transport |
| **Balances and disturbances** | [`balances_and_disturbances/`](balances_and_disturbances/index.md) | Column mass balance checks, harvest and cutting, fire, tillage, fertilizer |
| **I/O and forcing** | [`io_and_forcing/`](io_and_forcing/index.md) | Namelist and file readers (the plant and microbial parameter readers), forcing, history output and the producing assignment of each calibration target |
| **Diagnostics** | [`diagnostics/`](diagnostics/index.md) | Balance checks and diagnostic output |

## What changed at `cb243228`, and what the `2dea74d9` wiki had wrong

The rows below are the ones a calibration depends on. "Already wrong" means the old wiki misdescribed its own pin; "changed" means the source moved.

| Area | At `cb243228` | Kind | Page |
|---|---|---|---|
| Plant parameter reader | The live reader is `ReadPlantTraitTable`, copied per PFT by `SetPlantTraits`; the per-PFT reader `ReadPlantTraitsNC` is never called, so a name it alone reads (`RSRA`) is never read | already wrong | [`io_and_forcing/input_readers.md`](io_and_forcing/input_readers.md) |
| Root axial resistance | Derived from `ARSRA`, `RVSR` and `RRAD2M` in STARTQ: a per-vessel resistance for the primary and medium roots, divided by `NumVessels` for the fine roots; the stalk term uses `RSSA` | changed | [`plant_bgc/roots_and_uptake.md`](plant_bgc/roots_and_uptake.md) |
| Plant mass balance | An hourly per-PFT abort on C, N or P, not a debug check; it now counts root layers to `MAX(MaxNumRootLays, MaxSoilLays4Root_pft)` | already wrong; changed | [`plant_bgc/roots_and_uptake.md`](plant_bgc/roots_and_uptake.md) |
| `MaxSoilLays4Root_pft` | With dynamic phenology, the deepest root-tip layer capped at `NK`; it equals `NK` by assignment only under `ldo_sp_mode` | already wrong | [`plant_bgc/roots_and_uptake.md`](plant_bgc/roots_and_uptake.md) |
| `NPP_pft` | Carries gross fixation: respiration is still zero when it is formed; `ECO_NPP_col` is the net production | already wrong | [`plant_bgc/photosynthesis_and_respiration.md`](plant_bgc/photosynthesis_and_respiration.md) |
| Photosynthetic capacity | `VCMX`, `VOMX` are multiplied by 1.92 and `ETMX` by 1.35 at read | already wrong | [`plant_bgc/photosynthesis_and_respiration.md`](plant_bgc/photosynthesis_and_respiration.md) |
| `ZTYPI` | A continuous temperature offset `2.667*(2.5-ZTYPI)` on every plant Arrhenius function and the leaf-out/off thresholds, despite its zone labels | already wrong | [`plant_bgc/phenology.md`](plant_bgc/phenology.md) |
| Root growth | `Grow1stRootAxes` is gone; `SecondaryGrowthZone` has no live caller; `DMRT` enters both growth respiration and the nutrient-limited growth allowance | changed | [`plant_bgc/roots_and_uptake.md`](plant_bgc/roots_and_uptake.md) |
| Shoot-root exchange | `PTSHT` is the transfer conductance in `ShootRootElmTransfer`, which the old wiki never mentioned | already wrong | [`plant_bgc/roots_and_uptake.md`](plant_bgc/roots_and_uptake.md) |
| Leaf stoichiometry | Leaf N:C is not blended with stalk N:C; the grain partition goes to the stalk reserve at the reserve N:C | already wrong | [`plant_bgc/growth_and_allocation.md`](plant_bgc/growth_and_allocation.md) |
| Drought leaf-off | -2 MPa for every vascular plant type; cold-and-drought leaf-off triggers on either condition | changed; already wrong | [`plant_bgc/phenology.md`](plant_bgc/phenology.md) |
| Microbial mortality and sorption | Mortality is capped at the existing biomass; `HSORP` scales the sorbent capacity (more sorption), the opposite of the old form | changed; already wrong | [`microbial_bgc/decomposition_and_som.md`](microbial_bgc/decomposition_and_som.md) |
| Soil-to-plant nutrients | Microbial mineralization and root uptake draw on the same soil NH4, NO3 and phosphate pools in the same transport routine | not documented before | [`microbial_bgc/soil_plant_nutrient_coupling.md`](microbial_bgc/soil_plant_nutrient_coupling.md) |
| Microbial and solute models | Called every hour from the main driver | already wrong | [`apis/index.md`](apis/index.md) |
| Evapotranspiration | Transpiration is driven by reference-height air, not canopy air; `ECO_ET_col` is a within-year cumulative of ground and vegetation terms | already wrong | [`hydrotherm/surface_energy_balance_and_snow.md`](hydrotherm/surface_energy_balance_and_snow.md) |
| Phosphorus sorption | Inert on a fresh (non-restart) run: the soil branch of the chemistry initialisation is unreachable | changed | [`geochem/equilibria_and_sorption.md`](geochem/equilibria_and_sorption.md) |
| Run failure | Every `ENDRUN` ends in a plain `stop`, so an aborted run exits with status 0; detect failure from `ENDRUN:` in stdout and the last history sample | already wrong | [`drivers/ecosim_main.md`](drivers/ecosim_main.md) |
| Initialisation | STARTS, STARTQ and STARTE run only in the start year | already wrong | [`core/main_orchestration.md`](core/main_orchestration.md) |

## How to read citations

Citations appear as `(path/from/repo/root.F90:NNN)` or `:NNN-MMM`, at commit `cb243228`. Where a parameter's use is cited, the enclosing subroutine is named; where a parameter is read in parallel implementations selected by a type flag (C3 and C4 photosynthesis, woody and non-woody roots), the branch is named too. Fortran submodule bodies (`module procedure`) count as routines.

## Keeping it true

The three `reference/` maps are generated, not written: regenerate them with `python tools/ecosim_param_source_map.py --model-path $A2MC_MODEL_PATH --commit cb243228 --seed models/ecosim/curated_seed.yaml --markdown <this wiki>/reference/calibration_parameter_source_map.md --outputs-markdown <this wiki>/reference/curated_output_source_map.md --mechanisms-markdown <this wiki>/reference/curated_mechanism_index.md`. `tools/check_ecosim_tested_params_in_kb.py` fails when any of them is stale, when a tested parameter has no wiki row that cites a line together with its enclosing routine, or when a citation does not resolve at this commit; `tools/check_ecosim_seed_citations.py` holds the curated seed to the same standard.
