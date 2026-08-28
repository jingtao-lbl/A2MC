# ATS adapter (`models/ats/`)

A2MC adapter for **ATS** (the [Advanced Terrestrial Simulator](https://github.com/amanzi/ats)) —
a C++ integrated surface-subsurface hydrology model built on the Amanzi framework.

**Status: v0.1 (standalone-ATS target).** Parameter/output parsing, parameter-file writing,
and version-association are implemented and smoke-tested against real decks. The backend's
run-execution methods are functional-minimal (encode the real `ats <deck>.xml` run shape; the
run-template + observation-injection polish is deferred). Curated seed + RAG index are follow-ups.

## Why ATS is different

ATS breaks A2MC's two ELM-FATES-shaped assumptions:

| | ELM-FATES | ATS |
|---|---|---|
| Parameters | one NetCDF/JSON file, bare names | scattered Teuchos **ParameterList XML**, addressed by path, region-keyed, units-in-name |
| Outputs | NetCDF history tape | **observation `.dat`** time series, must be pre-declared in the deck |
| Run | CIME `case.submit` | `ats <deck>.xml` (MPI), one workdir per case |
| Source | Fortran | C++ |

## Files

| File | Role |
|---|---|
| `spec.py` | `ATS_SPEC` — identity, param/output regexes + categories, C++ source conventions, version dispatch |
| `parameter_parser.py` | `ATSParameterParser` — flattens an XML deck into `{address: record}`; shared address helpers (`iter_parameters`, `format_address`, `set_parameter_values`) |
| `output_parser.py` | `ATSOutputParser` — reads the deck's `observations` block (primary) or an observation `.dat` header |
| `version.py` | `ATSVersion` / `ATSVersionDetector` / `ATSBumpTierClassifier` / `ATSMilestoneMetadata` — `ats-X.Y.Z` tag + git commit |
| `backend.py` | `ATSBackend` — parse/write (complete), create_case/submit/status/extract (v0.1) |
| `prompts.py` | `DOMAIN_SUMMARY` + calibration hints (single source of truth) |
| `datasets.py` | `ATS_DATASETS` — the `ats-42b0e940` milestone bundle |
| `tests/fixtures/` | Real input decks (COMPASS oakharbor_{column,transect}, ats-demos priestley_taylor) for parser tests |

## Parameter addressing

A knob is addressed by its full ParameterList path, e.g.:

```
state/evaluators/permeability/value
state/model parameters/WRM parameters/computational domain/van Genuchten alpha [Pa^-1]
```

Region multiplicity is real: the same physical parameter recurs once per mesh region/material,
so the address (not the bare leaf name) is the unique key. `write_parameter_file` sets values by
this address and fails loud on any address not found.

## Calibration knobs (physical categories)

`water_retention` (van Genuchten α/n, residual saturation), `permeability`, `porosity`
(+ compressibility), `surface_flow` (Manning), `evapotranspiration` (Priestley-Taylor α,
rooting depth). `ATSParameterParser.calibration_parameters()` returns only these.

## Quick check

```python
import models.ats                      # registers the adapter
from models.ats.parameter_parser import ATSParameterParser
from models.ats.output_parser import ATSOutputParser

p = ATSParameterParser().parse("models/ats/tests/fixtures/priestley_taylor.xml")
o = ATSOutputParser().parse("models/ats/tests/fixtures/oakharbor_transect.xml")
```

## Wiki validation

The wiki (`docs/ats-knowledge-base/ats-codebase-wiki-<commit>`) is gated by two tools:

- **Generic V1** — `tools/validate_wiki_vs_source.py --model ats --wiki <dir> --source <ats-anchor-worktree>`:
  every `file:line` citation must resolve. (Its C/D checks report Amanzi out-of-scope refs as
  "unresolved" — see below.)
- **ATS series** — `tools/validate_ats_wiki.py --wiki <dir> --source <ats-anchor-worktree>`: three
  ATS-shaped checks the generic tool can't do — **S1** classifies unresolved refs against the
  spec's Amanzi boundary (`spec.external_symbol_names` / `external_module_patterns`) so the
  verdict is honest; **S2** every page carries a `Source pin` + `Last verified` at the pinned
  commit; **S3** every quoted **factory/type key** exists as a source string literal (catches a
  wrong PK-type string that passes citation checks but breaks an input deck).

`--source` must be the **pinned anchor worktree** (`ats_at_<commit>`), not the sibling `ats/`
checkout — the latter tracks upstream `master` and drifts away from the wiki pin, so validating
against it would silently check the wiki against the wrong tree. See the anchor/worktree layout in
`memory/dev_logs_adapterkitats/20260731a_ATS_Fork_Only_Push_Guard_And_Anchor_Branch_Wired.md`.

Both pass on the current wiki. A **Workflow B semantic audit** (2026-07-27) also verified each
page's prose against source and fixed real defects citation-checking missed (wrong factory keys,
a corrupted class name, an `elm_ats_api` argument inversion) — see
`docs/ats-knowledge-base/wiki_source_validation_42b0e940.md`.

## Next steps (onboard-model arc)

- V1 re-run: `tools/validate_wiki_vs_source.py --model ats` (needs an ATS source checkout).
- Curated seed (step 7): WRM/permeability/Manning/ET → water-balance targets.
- RAG build + milestone `ats-42b0e940` (step 9).
- Run template + smoke test (steps 11-13); use case (step 14): oakharbor_column → coweeta.
- Coupled ELM-ATS (COMPASS) is phase 2 — reuses this adapter, adds an ELM-namelist path and a
  Perlmutter/SLURM machine definition.

See `memory/dev_logs_adapterkit/20260727c_Scoping_ATS_Onboarding_Exploration.md`.
