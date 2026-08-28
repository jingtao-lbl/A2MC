# `use_cases/` — one folder per calibration case, and one template per model

A **case** is a model paired with a site: everything A2MC needs to calibrate `<Model>` at `<Case>`, and everything that calibration produced. A **template** is the seed a new case of that model is scaffolded from.

## Naming: `{Model}_{Case}`

The model slot names the **pairing that is actually run**, not just the vegetation or transport code. `ELM-FATES_Kougarok`, not `FATES_Kougarok` — FATES runs under several host land models and here the host is ELM, which is what the config, the spin-up protocol and the CIME settings assume.

## What is here

Which of these you actually see depends on the repo. Collaborator case studies are delivered to the group that owns each one rather than through a shared repo (see **Contributing a case** at the end), so a released checkout carries the templates plus the PI's own worked reference and the rows below thin out accordingly.

| folder | model | targets | what it is |
|---|---|---|---|
| [`EcoSIM_template/`](EcoSIM_template/) · [`ELM-FATES_template/`](ELM-FATES_template/) · [`PFLOTRAN_template/`](PFLOTRAN_template/) · [`ATS_template/`](ATS_template/) | per model | — | the **authored seed** for a new case of that model |
| [`TEMPLATE/`](TEMPLATE/) | — | — | the **shared fallback** seed, flat and model-prefixed. Reached only for a model with no template of its own, which today is none |

## Creating a case

Do not copy a folder by hand. The scaffolder resolves the right seed, renames the per-model files and deletes the rest:

```bash
python tools/create_use_case.py --model ecosim --case BioCON --dry-run   # always dry-run first
python tools/create_use_case.py --model ecosim --case BioCON
python tools/create_use_case.py --model fates --case Toolik --seed ELM-FATES_Kougarok   # seed from a worked case
```

**The full arc is the `onboard-case` skill**, which does the interview, the research plan, the parameter list and the readiness gate around that command. `python tools/create_use_case.py --list` shows every model key, its case-folder prefix and whether a template exists.

**Seeding is by `shutil.copytree` from the model's own `<Prefix>_template/`** when one exists. So anything added to a template — including the folder structure and its READMEs — is inherited by every future case of that model.

## The folder set inside a case

Every case carries the same ten folders, and **each one has its own `README.md` naming the skills that govern work in it**. Read that file before touching the folder; the case's own `README.md` carries the index.

```
<Model>_<Case>/
├── config/              what a session SOURCES — site + round configs, the round ledger
├── parameters/          per-round parameter lists and sampled design matrices
├── validation/          targets.yaml (the SPEC) + data/ (every raw observation)
├── case_template/       the files staged into every case directory
├── scripts/             canonical script TEMPLATES, copied into a phase folder and adapted
├── reports/             project-team-facing synthesis
└── memory/
    ├── logs/              the phase logs — the 3→4→5→6→3 reasoning chain
    ├── phase_results/     self-documenting artifact folders, sharing each log's stem
    ├── gained_knowledge/  the curated KB, behind a human gate
    └── model_evolution/   changes to the MODEL's source, and which round ran which binary
```

**`validation/` holds the spec; `validation/data/` holds the data.** A file is a calibration target if and only if `targets.yaml` names it — everything else in `data/` is a diagnostic you check the model against, never optimize toward. Adding a diagnostic to `targets.yaml` does not error; the round simply starts fitting it.

## Sourcing a case

One command. Since v2.306 the site config auto-loads the machine config its model needs and repairs the wrong one if it was sourced by mistake:

```bash
source use_cases/<Model>_<Case>/config/<case>_config.sh          # or the round wrapper, _r<N>.sh
echo "$A2MC_MAX_EXPERIMENTS $A2MC_MAX_SKIP_TESTING $A2MC_CONFIDENCE_THRESHOLD"   # none empty
```

## Which run-workflow skill

The phase skills (`phase0-design` … `phase6-refinement`) are model-agnostic; the procedure for actually running the model is not.

| model | skill |
|---|---|
| EcoSIM | `ecosim-run-workflow` |
| ELM-FATES | `offline-testing-workflow` |
| PFLOTRAN | `pflotran-run-workflow` |
| ATS | `ats-run-workflow` |

Above all of them, `calibration-goal` drives the loop and `calibration-discipline` says when a phase is actually finished rather than merely done.

## Contributing a case

**A case study is delivered to the group that owns it, and ships in no shared repo.** Collaborators fork the public repo and keep their case out of the fork, excluded via `.git/info/exclude` — never `.gitignore`, which is tracked and would publish the case's name. Publishing a case later is a pull request its owners decide. The rationale, and the alternatives that were rejected, are in `CLAUDE.md` §"Release and distribution model".
