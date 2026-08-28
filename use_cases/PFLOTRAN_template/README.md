# [Site Name] - A2MC PFLOTRAN Use Case

**Location:** [City/Region, Country]
**Coordinates:** [Lat, Lon]
**System:** [e.g., lysimeter, hillslope, column experiment]
**Status:** [Planning / Active / Complete]

PFLOTRAN is **deck-driven and standalone** (non-CIME): the parameter file IS the input deck,
plus a thermodynamic database. No ADSP/RGSP/TRANS phases, no `elm_options`, no PFT axis — its
grouping axis is the mesh **region** (a coupler name). See `models/pflotran/` for the adapter
and `docs/pflotran-knowledge-base/` for the source-grounded wiki.

---

## Folder map — and which skill governs each

**Every folder has its own `README.md` naming the skills to use when working in it.** Read that one before touching anything in the folder; this table is only the index.

| folder | purpose | skills that govern it |
|---|---|---|
| [`config/`](config/README.md) | what a session **sources** — site + round configs, the round ledger | `pflotran-run-workflow` · `phase0-design` · `model-evolution` |
| [`parameters/`](parameters/README.md) | per-round parameter lists and sampled design matrices | `phase0-design` · `literature-review` |
| [`validation/`](validation/README.md) | `targets.yaml` — everything scored, and what is deliberately not | `onboard-case` · `phase6-refinement` · `plotting` |
| [`case_template/`](case_template/README.md) | the files staged into every case | `pflotran-run-workflow` · `phase0-design` |
| [`scripts/`](scripts/README.md) | canonical script **TEMPLATES** — copied into a phase folder, never run in place | `plotting` · `calibration-discipline` |
| [`memory/logs/`](memory/logs/README.md) | the phase logs — the 3→4→5→6→3 reasoning chain | **`calibration-log`** · the phase skills |
| [`memory/phase_results/`](memory/phase_results/README.md) | self-documenting artifact folders, one per phase, sharing the log's stem | `plotting` · `calibration-log` |
| [`memory/model_evolution/`](memory/model_evolution/README.md) | changes to the MODEL's source, and which round ran which binary | **`model-evolution`** · `log` |
| [`memory/gained_knowledge/`](memory/gained_knowledge/README.md) | the curated KB — and the human gate in front of it | **`curate-knowledge`** · `inject-knowledge` |
| [`reports/`](reports/README.md) | project-team-facing synthesis, tracing back to the logs and artifacts | **`write-report`** · `summarize-calibration-round` |

**Above all of them:** `calibration-goal` drives the loop, and `calibration-discipline` says when a phase is actually finished rather than merely done.

## Overview

Brief description of the system and calibration goals.

---

## Model setup

- **Mesh / regions:** [describe the domain and the named regions/couplers outputs are written at]
- **Forcing:** [e.g. a rainfall/flux time series]
- **Database:** [the thermodynamic database this deck uses]

---

## Validation Targets

`validation/targets.yaml` targets are `variable`/`denominator`/`reduce`/`region`/`window` dicts
(PFLOTRAN has no `PFT<id>_<vartype>` bare-key convention — that is FATES-only, and no PFT axis at
all). A common pattern for a mass-balance/coupler output: score a **concentration ratio**
(`reduce: outflow_concentration`, `variable` over `denominator`) so an unresolved area/scale
normalization cancels out rather than contaminating the fit — see
`models/pflotran/backend.py`'s `reduce_derived` seam before assuming a reduce mode applies.
`window` is in **hours**, not row indices (a common footgun — see
`use_cases/PFLOTRAN_miniLEO/validation/targets.yaml`'s header for the concrete incident).

| Target | Variable | Denominator | Reduce | Observed | Uncertainty | Source |
|---|---|---|---|---|---|---|
| `[name]` | `"[coupler] [Species] [mol/h]"` | `"[coupler] Water Mass [kg/h]"` | outflow_concentration | X.XXXXe-XX mol/L | ±XX% | [Citation] |

---

## Data Sources

- **Observations:** [Source/Citation — measurement bundle, sampling window]
- **Forcing:** [Source]
- **Mesh / geometry:** [Source, e.g. the `.h5` mesh file]

---

## Configuration

Key site-specific parameters (see `config/<model>_<case>_config.sh`, sourced after
`a2mc_noncime_config.sh` — **not** `a2mc_config.sh`, which is for the CIME-driven models):

```bash
export A2MC_SITE_NAME="[Site Name]"
export A2MC_MODEL_PATH="[path to the PFLOTRAN checkout]"
export A2MC_PFLOTRAN_DECK="[path to the base .in deck]"
export A2MC_PFLOTRAN_DATABASE="[path to the thermodynamic database]"
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
