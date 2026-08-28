# [Site Name] - A2MC EcoSIM Use Case

**Location:** [City/Region, Country]
**Coordinates:** [Lat, Lon]
**Ecosystem:** [e.g., Arctic tundra, Boreal forest, Temperate grassland]
**Status:** [Planning / Active / Complete]

EcoSIM is a **standalone, namelist-driven binary** — no CIME case scripts, no ADSP/RGSP/TRANS
phases, no `elm_options`. It runs single-continuous, one `srun -n 1` per case (OMP=1, mpi=0),
against a **per-PFT NetCDF** parameter file. See `models/ecosim/` for the adapter and
`docs/ecosim-knowledge-base/` for the source-grounded wiki.

---

## Folder map — and which skill governs each

**Every folder has its own `README.md` naming the skills to use when working in it.** Read that one before touching anything in the folder; this table is only the index.

| folder | purpose | skills that govern it |
|---|---|---|
| [`config/`](config/README.md) | what a session **sources** — site + round configs, the round ledger | `ecosim-run-workflow` · `phase0-design` · `model-evolution` |
| [`parameters/`](parameters/README.md) | per-round parameter lists and sampled design matrices | `phase0-design` · `literature-review` |
| [`validation/`](validation/README.md) | `targets.yaml` — everything scored, and what is deliberately not | `onboard-case` · `phase6-refinement` · `plotting` |
| [`case_template/`](case_template/README.md) | the files staged into every case | `ecosim-run-workflow` · `phase0-design` |
| [`scripts/`](scripts/README.md) | canonical script **TEMPLATES** — copied into a phase folder, never run in place | `plotting` · `calibration-discipline` |
| [`memory/logs/`](memory/logs/README.md) | the phase logs — the 3→4→5→6→3 reasoning chain | **`calibration-log`** · the phase skills |
| [`memory/phase_results/`](memory/phase_results/README.md) | self-documenting artifact folders, one per phase, sharing the log's stem | `plotting` · `calibration-log` |
| [`memory/model_evolution/`](memory/model_evolution/README.md) | changes to the MODEL's source, and which round ran which binary | **`model-evolution`** · `log` |
| [`memory/gained_knowledge/`](memory/gained_knowledge/README.md) | the curated KB — and the human gate in front of it | **`curate-knowledge`** · `inject-knowledge` |
| [`reports/`](reports/README.md) | project-team-facing synthesis, tracing back to the logs and artifacts | **`write-report`** · `summarize-calibration-round` |

**Above all of them:** `calibration-goal` drives the loop, and `calibration-discipline` says when a phase is actually finished rather than merely done.

## Overview

Brief description of the site and calibration goals.

---

## Plant functional types

| PFT (input name) | Type flags | Group | Description |
|---|---|---|---|
| `[pft_name]` | `[ICTYP/INTYP flags]` | `[C3/C4/legume/...]` | `[Description]` |

Type-flag identity is not stable across EcoSIM versions — verify each PFT's flags in the actual
per-PFT input file, not from a name (see `docs/ecosim-knowledge-base/ecosim_plant_parameter_reference.md`
if present for your checkout).

---

## Validation Targets

`validation/targets.yaml` targets are `variable`/`reduce`/`observed` dicts (EcoSIM has no
`PFT<id>_<vartype>` bare-key convention — that is FATES-only). Common `reduce` values seen in
`models/ecosim/backend.py`: `annual` (a calendar-year sum/mean), `sum_pft_peak` (peak standing
stock, summed across PFTs and variables), `growing_season_mean_abs` (May-Sep mean of an
absolute-valued flux, e.g. `CO2_SEMIS_FLX_col` for soil respiration), `depth_integral` (a
soil-layer stock integrated over a depth range). Check `models/ecosim/backend.py::reduce_ecosystem`
for the full, current list before assuming one applies.

| Variable | Reduce | Observed | Uncertainty | Source |
|----------|--------|----------|-------------|--------|
| `NPP_pft` | annual | XXX gC/m2/yr | ±XX% | [Citation] |
| `SHOOT_C_pft` + `Root_C_pft` | sum_pft_peak | XXX gC/m2 | ±XX% | [Citation] |
| `CO2_SEMIS_FLX_col` (Fs) | growing_season_mean_abs | X.X umol CO2/m2/s | ±XX% | [Citation] |
| `tSOC_vr` (per depth band) | depth_integral | XXX gC/m2 | ±XX% | [Citation] |

---

## Data Sources

- **Plant/soil observations:** [Source/Citation]
- **Climate forcing:** [Source, e.g. NARR]
- **PFT input file:** [Source of the per-PFT parameter values]

---

## Configuration

Key site-specific parameters (see `config/<model>_<case>_config.sh`, sourced after
`a2mc_noncime_config.sh` — **not** `a2mc_config.sh`, which is for the CIME-driven models):

```bash
export A2MC_SITE_NAME="[Site Name]"
export A2MC_SITE_LAT=XX.XX
export A2MC_SITE_LON=XX.XX
export A2MC_MODEL_PATH="[path to the EcoSIM checkout]"
export A2MC_BASE_PARAM_FILE="[path to the base per-PFT NetCDF input]"
```

---

## Key Findings

Document discoveries and lessons learned during calibration.

### Discovery 1: [Name]

**Description:** ...

**Mechanism:** ...

**Affected parameters:** ...

---

## Files

| File | Description |
|------|-------------|
| `config/<model>_<case>_config.sh` | Site configuration (sourced after `a2mc_noncime_config.sh`) |
| `config/calibration_rounds.yaml` | Per-round record (parameters, ensembles, outcome) |
| `parameters/*.csv` | Morris/Sobol parameter list |
| `validation/targets.yaml` | Calibration targets + reduce/window + cost config. See `docs/24_Generic_Obs_Comparison_Plan.md` |

---

## References

- [Relevant publications]
- [Data sources]
