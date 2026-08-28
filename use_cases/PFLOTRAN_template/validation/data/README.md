# `validation/data/` — all raw observational data for this case

**Every raw data file lives here, whatever its role** — calibration and validation alike. The
*role* is decided by `../targets.yaml`, not by where the file sits.

```
use_cases/<Model>_<Case>/validation/
├── targets.yaml     # the SPEC: what is scored. Calibration-only.
└── data/            # the DATA: every raw observation file, both roles
```

## The one distinction that matters

| | Calibration | Validation / diagnostic |
|---|---|---|
| What it is | what the model must **MATCH** | what you **CHECK** the model against |
| Scored? | **yes** — drives parameter optimization | **no** — never enters the scoring path |
| Declared in `targets.yaml`? | **yes** | **no** |
| Format | whatever the source provides | whatever the source provides |
| Read by | the scoring path, via `targets.yaml` | purpose-built analysis scripts |

**Both kinds of file live in this folder.** What makes an observation a calibration target is that
`targets.yaml` names it — nothing else. So the test to apply before adding data is not "where does
this go" but:

> **Must the model MATCH this, or am I only checking it?**

Get that wrong in the *scored* direction and nothing errors: the round silently begins optimizing
toward data you meant as a cross-check, and every artifact — screening table, sensitivity ranking,
cost trajectory — still looks correct.

## Why the parent folder is called `validation/`

Historical. `validation/` holds `targets.yaml`, which is **calibration**, so the folder name says
the opposite of what its main file does. Do not read the folder name as the role — read
`targets.yaml`.

## Long time-series calibration targets: reference, do not inline

`targets.yaml` takes scalars, snapshots and **short** observation series inline. A long time series
(hundreds of points) does **not** belong in an inline `observations:` list — put the data in this
folder and have the target reference it by **path + reader**. Inlining it makes the spec unreadable
and duplicates data that already exists as a file, which is the drift this split exists to prevent.

## The role question is model-agnostic; the target GRAMMAR is not

This folder works the same for every onboarded model. How a target *names* what it scores does not:
ELM-FATES uses `PFT<id>_<vartype>` / `ECO_` / `SNOW_` / `SOIL_` keys, while an adapter model
(EcoSIM, PFLOTRAN, ATS) uses `variable` / `reduce` / `window_years` resolved against **its own
output registry**. Ask the granularity question in your model's own terms — see `onboard-case`
Step 1.1 — and validate with the tool for your model, since the two validators are not
interchangeable.

## Conventions

- **One subfolder per source** (`modis/`, `fluxnet/`, `field_plots/`), each with its own `README.md`
  giving provenance: where the data came from, when it was retrieved, units, and any processing
  already applied.
- **Keep the native format.** CSV, NetCDF, `.mat`, fixed-width — no reformatting on the way in.
  Readers adapt to the data, not the reverse.
- **Never invent a value.** If a number is not in a source file, it is not an observation.
- **Cite the file, not the number.** A target or a report references the path; a copied literal
  loses its provenance the moment the source is corrected.
- **Record which source plays which role in THIS case.** Add a case-level note here when a source is
  deliberately not wired into scoring, so the omission reads as a decision rather than an oversight.
