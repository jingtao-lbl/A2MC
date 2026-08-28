# ATS case TEMPLATE

Copy this directory to `use_cases/ATS_<YourCase>/` and work through it. It is the ATS
counterpart of `use_cases/PFLOTRAN_template/` and `use_cases/EcoSIM_template/`.

**Created 2026-08-25, and the reason is worth knowing before you use it.** `models/ats/`
has shipped a complete adapter — spec, backend, parameter parser, output parser, datasets,
prompts, 1141 lines — with **no case at all**, while EcoSIM and PFLOTRAN each had a
template. So nothing in the repo exercised that adapter end to end, and a user onboarding
ATS had no starting point. This closes the second half; the first half is still open, and
§"What is not proven" below says exactly how far.

## Folder map — and which skill governs each

**Every folder has its own `README.md` naming the skills to use when working in it.** Read that one before touching anything in the folder; this table is only the index.

| folder | purpose | skills that govern it |
|---|---|---|
| [`config/`](config/README.md) | what a session **sources** — site + round configs, the round ledger | `ats-run-workflow` · `phase0-design` · `model-evolution` |
| [`parameters/`](parameters/README.md) | per-round parameter lists and sampled design matrices | `phase0-design` · `literature-review` |
| [`validation/`](validation/README.md) | `targets.yaml` — everything scored, and what is deliberately not | `onboard-case` · `phase6-refinement` · `plotting` |
| [`case_template/`](case_template/README.md) | the files staged into every case | `ats-run-workflow` · `phase0-design` |
| [`scripts/`](scripts/README.md) | canonical script **TEMPLATES** — copied into a phase folder, never run in place | `plotting` · `calibration-discipline` |
| [`memory/logs/`](memory/logs/README.md) | the phase logs — the 3→4→5→6→3 reasoning chain | **`calibration-log`** · the phase skills |
| [`memory/phase_results/`](memory/phase_results/README.md) | self-documenting artifact folders, one per phase, sharing the log's stem | `plotting` · `calibration-log` |
| [`memory/model_evolution/`](memory/model_evolution/README.md) | changes to the MODEL's source, and which round ran which binary | **`model-evolution`** · `log` |
| [`memory/gained_knowledge/`](memory/gained_knowledge/README.md) | the curated KB — and the human gate in front of it | **`curate-knowledge`** · `inject-knowledge` |
| [`reports/`](reports/README.md) | project-team-facing synthesis, tracing back to the logs and artifacts | **`write-report`** · `summarize-calibration-round` |

**Above all of them:** `calibration-goal` drives the loop, and `calibration-discipline` says when a phase is actually finished rather than merely done.

## ★ Every value in here is a placeholder, on purpose

Structure is wired; values are **not**. `targets.yaml` carries `observed: null` on every
target, the config carries `<PLACEHOLDER>` on every path, and the parameter list has only
commented example rows.

That is the project's convention, not laziness: **wire the structure with null values and
let the RED gate be the deliverable** ([[feedback_placeholder_targets_structure_not_values]]).
A target with a plausible invented number is worse than a missing one, because it scores.
A fabricated parameter list is worse than none, because it looks like a starting point.

## What ATS does differently from every other onboarded model

| | ATS |
|---|---|
| **Run style** | standalone C++ binary, **non-CIME** → source `a2mc_noncime_config.sh`, never `a2mc_config.sh` ([[feedback_two_machine_configs_cime_vs_noncime]]) |
| **Parameter file** | an **XML ParameterList deck**. A knob is a full path address (`a/b/c/leaf`), so `name` contains slashes, spaces and bracketed units |
| **Grouping axis** | **`region`** — the mesh region / material. No PFT axis at all (`spec.py`: `grouping_axis="region"`, `default_groups=()`) |
| **Outputs** | ATS writes its own observations; no host-model variables (`key_external_outputs=()`) |

### The grouping axis, and a verified consequence

ATS is the **third** axis type in this kit, after EcoSIM/FATES's integer PFT and PFLOTRAN's
mineral names. Per the canonical template's axis rule, carry the region name in the `pft`
column as the documented single-axis stopgap and declare the real axis — do **not** rename
`pft`.

**Verified 2026-08-25 against a region-axis list** (`tests/test_bound_source_vocabulary.py`):

- `tools/check_bound_source.py` **reads it**.
- `tools/param_spec.load_param_spec` **raises** on it (`pft='upland' is not an integer`),
  exactly as it does for PFLOTRAN's minerals.

So use the sampler path (`scripts/create_adapter_parameter_sample.py`, which is
column-name based), not the canonical loader.

## What is in here

| Path | What it is |
|---|---|
| `config/ats_template_config.sh` | the site config. Every `<PLACEHOLDER>` is deliberate |
| `config/calibration_rounds.yaml` | the round record, with the `model_change_ledger` shape pre-wired |
| `parameters/parameter_list_template.csv` | the parameter list, with the five-prefix `bound_source` vocabulary and commented examples only |
| `validation/targets.yaml` | the targets, every `observed` null |

## Getting started

```bash
cp -r use_cases/ATS_template use_cases/ATS_<YourCase>
source a2mc_noncime_config.sh                                   # NON-CIME
source use_cases/ATS_<YourCase>/config/ats_<yourcase>_config.sh
python tools/check_stage_ready.py                               # which setup stage am I in?
```

Then work the `onboard-case` skill. Its interview → research plan → parameter list →
Phase 0 arc is model-agnostic and applies here unchanged.

## What is NOT proven — read this before assuming a full round runs

`models/ats/backend.py` states its own maturity in its class docstring:

> *"Standalone-ATS backend. Parameter/output I/O is complete; run wiring is v0.1."*

Parameter parsing, output parsing and the spec are real and tested. The
**submit / monitor / extract path is not proven end to end**, because until this template
there was no ATS case to prove it with. Treat the first real case as onboarding the *run
path* as well, and log what it takes — that is the gap this template exists to let someone
close, and it will not close itself.

Two more things a first case will need that are not here, because both require domain
content that would be fabrication to invent:

1. **Real parameters, bounds and their `bound_source` provenance.** The five-prefix
   vocabulary is documented in the parameter list's own header.
2. **Real observations** for `targets.yaml`, with a `reduce` keyword confirmed against
   `models/ats/backend.py`. An **unregistered** reduce keyword is the dangerous case: it
   does not raise, it falls through to a snapshot and returns a plausible wrong number
   (measured on EcoSIM, v2.247). If a target has no valid reducer, leave it undeclared and
   say so in `not_yet_declared`.

## Related

- `models/ats/spec.py` — the parameter and output categories, the mechanism map, the axis
- `use_cases/PFLOTRAN_template/` — the sibling non-CIME template this one mirrors
- `use_cases/EcoSIM_BioCON/` — a real, worked adapter case, three rounds deep
