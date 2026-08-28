# `validation/` — the targets, and what is NOT a target

**`targets.yaml` is the calibration surface: everything scored, and nothing else.** Scoring goes through a target's own `reduce` — never a reimplementation — or the number disagrees with the round's for a reason no reader can see.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| setting up a new case's targets | **`onboard-case`** |
| the sim-vs-obs figure covering every scored target | `pflotran-run-workflow`, with **`plotting`** |
| scoring a variant set against these | **`phase6-refinement`** |
| observations still pending | wire the **structure** with `observed: null` — the RED gate is the deliverable |

## The distinction this folder exists to hold

| | |
|---|---|
| **`targets:`** | **scored.** These and only these drive the calibration |
| **`prescribed_initialization:`** | **NOT scored.** Anything the run's initial state is BUILT FROM. Scoring an input rewards the input |

`validate_model_targets.py` raises if a name appears in both.

## This model's target shape

Targets are named for the quantity (`outflow_Ca`, `hydrograph`), not for a PFT, and are anchored by `window`/`window_years`. Outputs come from `*-mas.dat` columns and Tecplot snapshots -- **there is no NetCDF history tape**.

## Known traps

- **PFLOTRAN reports **model time**, and the observation window may be offset from it. On miniLEO measured hour 0 is MODEL hour 806, so a window written as [0, 768] in model time contains **zero** observations and does contain spin-up.**
- **A partially covered window is an ERROR, not a smaller sample.** Early termination is caused by instability, so the surviving tail is biased toward the blow-up. Census the record before scoring anything.
- **Say which window a number came from.** Spin-up years are not comparable to a target, and naming the window is the cheapest way to keep that straight.

```bash
python tools/validate_model_targets.py --model pflotran --targets validation/targets.yaml
```
