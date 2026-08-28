# Wiki-Source Validation (ecosim): ecosim-codebase-wiki-2dea74d9 vs EcoSIM

**Generated:** 2026-07-12T05:50:49Z

**Model:** `ecosim`  (source extensions: .F90, .f90)
**Wiki:** `docs/ecosim-knowledge-base/ecosim-codebase-wiki-2dea74d9`
**Source:** the EcoSIM checkout on shared project space (such as `/global/cfs/cdirs/<project>/<user>/EcoSIM`); the exact path is machine-specific

---

## Summary

- Wiki pages: 41
- Source files: 586
- Declared routines indexed: 3581

| Check | Status | Pass / Total |
|---|---|---|
| A. File-citation existence | green | 1241/1241 |
| B. Line-bound validity | green | 1241/1241 |
| C. Routine-reference presence | green | 54/55 |
| D. Module-file presence | green | 119/124 |

**Overall verdict:** Green

(Green = all checks >= 90% pass; Yellow = any check 70-90%; Red = any check < 70%)

---

## Per-page results

| Wiki page | Band | Files | Routines | Overall |
|---|---|---|---|---|
| `io_and_forcing/input_readers.md` | green | 49/49 | 2/3 | 98% |
| `apis/api_data.md` | green | 24/24 | 4/4 | 100% |
| `apis/api_layer.md` | green | 35/35 | 2/2 | 100% |
| `apis/index.md` | green | 18/18 | 4/4 | 100% |
| `balances_and_disturbances/disturbances.md` | green | 28/28 | 0/0 | 100% |
| `balances_and_disturbances/index.md` | green | 11/11 | 0/0 | 100% |
| `balances_and_disturbances/mass_balance.md` | green | 32/32 | 1/1 | 100% |
| `core/grid_and_mesh.md` | green | 12/12 | 0/0 | 100% |
| `core/index.md` | green | 3/3 | 2/2 | 100% |
| `core/main_orchestration.md` | green | 24/24 | 7/7 | 100% |
| `core/model_config.md` | green | 20/20 | 6/6 | 100% |
| `core/utilities.md` | green | 23/23 | 4/4 | 100% |
| `data_types/index.md` | green | 16/16 | 0/0 | 100% |
| `diagnostics/index.md` | green | 51/51 | 0/0 | 100% |
| `drivers/aquachem.md` | green | 2/2 | 1/1 | 100% |
| `drivers/ats_coupling.md` | green | 32/32 | 4/4 | 100% |
| `drivers/boxsbgc.md` | green | 5/5 | 1/1 | 100% |
| `drivers/ecosim_main.md` | green | 73/73 | 1/1 | 100% |
| `drivers/index.md` | green | 0/0 | 0/0 | 100% |
| `drivers/standalone_drivers.md` | green | 4/4 | 2/2 | 100% |
| `geochem/equilibria_and_sorption.md` | green | 46/46 | 0/0 | 100% |
| `geochem/index.md` | green | 34/34 | 0/0 | 100% |
| `hydrotherm/index.md` | green | 16/16 | 1/1 | 100% |
| `hydrotherm/subsurface_water_and_heat.md` | green | 45/45 | 0/0 | 100% |
| `hydrotherm/surface_energy_balance_and_snow.md` | green | 50/50 | 0/0 | 100% |
| `index.md` | green | 0/0 | 0/0 | 100% |
| `io_and_forcing/forcing.md` | green | 44/44 | 1/1 | 100% |
| `io_and_forcing/history_and_restart.md` | green | 77/77 | 2/2 | 100% |
| `io_and_forcing/index.md` | green | 30/30 | 2/2 | 100% |
| `microbial_bgc/decomposition_and_som.md` | green | 75/75 | 2/2 | 100% |
| `microbial_bgc/index.md` | green | 27/27 | 0/0 | 100% |
| `overview/index.md` | green | 30/30 | 0/0 | 100% |
| `overview/source_tree.md` | green | 2/2 | 0/0 | 100% |
| `plant_bgc/growth_and_allocation.md` | green | 53/53 | 1/1 | 100% |
| `plant_bgc/index.md` | green | 42/42 | 1/1 | 100% |
| `plant_bgc/phenology.md` | green | 54/54 | 1/1 | 100% |
| `plant_bgc/photosynthesis_and_respiration.md` | green | 65/65 | 0/0 | 100% |
| `reference/module_inventory.md` | green | 25/25 | 1/1 | 100% |
| `transport/gas_transport.md` | green | 24/24 | 0/0 | 100% |
| `transport/index.md` | green | 13/13 | 1/1 | 100% |
| `transport/solute_transport.md` | green | 27/27 | 0/0 | 100% |

---

## Cited files that do NOT exist in source

All cited source files exist.

---

## Referenced routines NOT found in source

### `io_and_forcing/input_readers.md`
| Routine | Mentions |
|---|---|
| `readsmod` | 1 |

---

## Cited lines beyond file length (0)

All cited line numbers are within file bounds.

---

## Module files mentioned but missing from source

| Module file | First wiki page |
|---|---|
| `DataMod.F90` | `balances_and_disturbances/mass_balance.md` |
| `FastMod.F90` | `balances_and_disturbances/mass_balance.md` |
| `MicBGCMod.F90` | `data_types/index.md` |
| `SlowMod.F90` | `balances_and_disturbances/mass_balance.md` |
| `ecosim_Time_Mod.F90` | `drivers/aquachem.md` |
