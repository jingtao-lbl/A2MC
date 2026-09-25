---
name: onboard-case
visibility: public
category: calibration
description: Create a NEW calibration case/project for a model that is ALREADY onboarded — the repeatable half of getting started. Interview from the science goal, draft the research plan, scaffold use_cases/{Model}_{Case}/ from that MODEL's site-agnostic template, build or vet the parameter list, run the readiness preflight, and hand off to Phase 0. Use when the user says "set up a new case", "add a site/project", "onboard my case", "calibrate <model> at <site>", "start a second case", or after onboard-model finishes. NOT for adding a MODEL (use onboard-model) and NOT for first-run machine setup in a fresh clone (use a2mc-init).
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [setup]
  summary: "Repeatable case/project onboarding for an already-onboarded model: interview -> bind + verify this case's model install -> scaffold use_cases/{Model}_{Case}/ from the per-model template -> research plan (GATE 1) -> param list (GATE 2) -> preflight -> Phase 0."
---

# Onboard a Case (a new site / project for an onboarded model)

The **repeatable** half of getting started. `onboard-model` adds a MODEL once; this adds a
CASE, and runs again for every new site, project or scenario on that model.

> ## Before Step 1 — three prerequisites, each with a check you can run
>
> | prerequisite | check | if it fails |
> |---|---|---|
> | **the clone is wired** | `python3 tools/check_clone_setup.py` exits 0 | `a2mc-init` Step 1 (a few minutes), then continue here |
> | **the model is onboarded** | ELM-FATES is built in; for an adapter model, `python3 tools/check_stage_ready.py --model <m>` shows `milestone registered` | `onboard-model`, which ends by handing back to this skill; a half-onboarded model resumes at its first failing row there |
> | **this is a new case** | `use_cases/{Model}_{Case}/` does not exist | it is a RESUME, not a new case: `python3 tools/check_stage_ready.py --case {Model}_{Case}` and continue from the first failing row. A case that already carries `memory/workflow_state_offline_r*.json` is past setup; that is `onboard-session`, **except** a **re-bind**: a delivered or rebuilt case that `onboard-session` sends here does Step 2 and Step 4(b) item 1 only (the model install and the site config's run fields), then goes back to `onboard-session`. Nothing else in a running case is redone |
>
> The model install on this machine (checkout, build, milestone match) is **not** a prerequisite:
> Step 2 below binds this case to it, and the machine config was written by `a2mc-init` Step 3.
> Onboarding a case on a model with no adapter produces a config pointing at parsers that do not
> exist, which is why the second row is a hard stop.

## Naming — `use_cases/{Model}_{Case}/`

> **Definition of done for this stage: `setup-discipline`.** This skill performs the stage; that one
> collects what "finished" means for it, with the executable gate per item. Check it before
> declaring this stage complete.


**One rule, and it is not optional.** The directory is `{Model}_{Case}`: `EcoSIM_BioCON`,
`PFLOTRAN_miniLEO`, `ATS_OakHarbor`. The model prefix is what lets one model host several cases
and keeps two models' sites from colliding.

**The model prefix is the DISPLAY prefix, not the model key.** `--model fates` produces
`ELM-FATES_<Case>`, because `create_use_case.py`'s `BUILTIN_PREFIXES` maps the key `fates` to the
prefix `ELM-FATES` — the pairing that is actually run is FATES *under ELM*. So `use_cases/ELM-FATES_Kougarok/`
is **the convention, not an exception** (it was renamed from `Kougarok/` on 2026-08-25). Verify rather than
assume: `python tools/create_use_case.py --model fates --case Toolik --dry-run` prints
`use_cases/ELM-FATES_template -> use_cases/ELM-FATES_Toolik`.

Seeding a new arctic case from Kougarok's **contents** is `--seed ELM-FATES_Kougarok` in Step 3 —
the seed is a **directory name**, so the bare `--seed Kougarok` this skill used to document now
resolves to nothing.

The site config inside is `config/<model>_<case>_config.sh`, lowercase.

## The template is PER MODEL and site-agnostic

**`use_cases/<Model>_template/` is the seed, and it is AUTHORED SOURCE** (architecture B, PI
2026-08-17). `create_use_case.py` defaults to it and copies it verbatim; it falls back to the shared
`use_cases/TEMPLATE/` only for a model that has not authored a dir yet.

| model | seed | run style |
|---|---|---|
| ELM-FATES | `use_cases/ELM-FATES_template/` | CIME |
| EcoSIM | `use_cases/EcoSIM_template/` | standalone binary + namelist |
| PFLOTRAN | `use_cases/PFLOTRAN_template/` | standalone binary + input deck + thermodynamic database |
| ATS | `use_cases/ATS_template/` | standalone binary + nested Teuchos ParameterList XML deck |

`python tools/create_use_case.py --list` prints this table from the tree, including the seed each
model would actually resolve — prefer it over this copy, which is a snapshot.

Each carries only what that model needs — config, `calibration_rounds.yaml`, `targets.yaml`,
README, and any run-control file its run style requires (EcoSIM ships `case_template/run.nml` plus
an `OPTIONS.md` reference). Replace every `<PLACEHOLDER>`.

> **These dirs used to be GENERATED snapshots of `TEMPLATE/`, regenerated and drift-tested.** That is
> why a per-model file could not live in one: the next regeneration deleted it, which is how every
> scaffolded EcoSIM case came to point at a `case_template/run.nml` that existed nowhere
> (`20260816a` F1). Under B, adding a per-model file is just adding a file — no
> `EXTRA_TEMPLATE_FILES` row, no suffix convention. **Do not regenerate these dirs; edit them.**

**Machine config vs site config — which file holds what.** The machine config was written once per
clone by `a2mc-init` Step 3: `a2mc_config.sh` for a CIME model, `a2mc_noncime_config.sh` for a
standalone one. Every shipped site config auto-sources the right one and repairs the wrong one, so
you never source it by hand ([[feedback_two_machine_configs_cime_vs_noncime]]). What differs by family
is where the **model install** lives:

| model | model checkout | binary | HPC account, output root |
|---|---|---|---|
| ELM / ELM-FATES (CIME) | `A2MC_E3SM_ROOT` in `a2mc_config.sh` (`A2MC_MODEL_PATH` defaults to it) | built per case by CIME | `A2MC_PROJECT`, `A2MC_OUTPUT_ROOT` in `a2mc_config.sh` |
| EcoSIM, PFLOTRAN, ATS | `A2MC_MODEL_PATH` in **this case's site config** | `A2MC_ECOSIM_BINARY` / `A2MC_PFLOTRAN_BINARY` / `A2MC_ATS_EXE` in the site config | `A2MC_HPC_ACCOUNT`, `A2MC_OUTPUT_ROOT` in the site config |

`a2mc_noncime_config.sh` deliberately sets none of the non-CIME row. Step 2 binds them.

**Shell variables used below.** Derive the root once and anchor every write to it; never write
through an unset prefix, which expands `$A2MC_ROOT/use_cases/...` to the filesystem root:

```bash
A2MC_ROOT="${A2MC_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null)}"
test -f "$A2MC_ROOT/a2mc_noncime_config.sh" || { echo "not in an A2MC clone — cd into it first"; exit 1; }
CASE_DIR="<Model>_<Case>"                  # e.g. EcoSIM_OakRidge; the rule is §Naming above
DEST="$A2MC_ROOT/use_cases/$CASE_DIR"
```

An agent must join these to the command that uses them (`A2MC_ROOT=... && ...`): each shell call is
a fresh process.

## Step 1 — Interview (start from the science goal, not the model internals)

**Do not assume the user knows FATES internals.** A new user often does not know which PFTs dominate their
site, what a parameter does, or even whether they need PFT-level detail at all. Start from what they *do*
know — their **science question and their data** — and derive the model configuration from it. Ask in grouped
rounds (use the harness's structured-question UI where available); never ask what you can read from the
repo/env — check first, then confirm.

**Offer the user a path first (a structured choice, each with a different next action):**

- **Path A — "I know my configuration and site"** (FATES/nutrient mode, PFTs, and targets are clear). → Go
  straight to the detail rounds **1A–1D** and **capture the setup** (site config + a session log; the
  "record the decisions" block below). This is the fast path.
- **Path B — "I'm new to this / not sure what I need."** → **Do not** start by asking for PFT ids or a
  parameter list. Start with **1.0 (goal + data)** — it decides which later questions even apply, so the user
  never has to answer a FATES-internals question they cannot.

### 1.0 — What are you calibrating? (this sets the *target granularity* — ask it first)

The granularity of the target decides everything downstream, **including whether the user needs to know their
PFTs at all.** Offer these options:

- **Ecosystem-level fluxes/states** — e.g. MODIS or eddy-covariance **GPP**, NEE, ET, ecosystem LAI, total
  aboveground biomass — aggregated over the whole gridcell / tower footprint. → **You do NOT need to
  enumerate dominant PFTs or per-PFT biomass.** The targets are ecosystem totals; the PFT composition is
  secondary (a reasonable default/mixed PFT set is fine, and a simpler FATES config — even ELM-SP for pure
  GPP — may suffice). **Skip 1.2.**
- **PFT- or species-level** — per-PFT leaf / fine-root / AGB biomass, per-PFT phenology, community
  composition. → The PFT set now matters; go to **1.2** to identify it.
- **Both / not sure yet** — go to **1.1** (data inventory) and let the data decide.

### 1.1 — Data inventory (for users unsure what they can calibrate)

Ask what observations they actually have, and for each: **source** (MODIS, a FLUXNET tower, a field plot,
literature…), **variable** (GPP, biomass, LAI, phenology…), **spatial scale** (gridcell / tower footprint /
plot / individual), **temporal** (single snapshot vs time series), **units**, **uncertainty**, and the
**year/month** measured. Then map each observation to a granularity:

- gridcell- or tower-aggregate flux/state → an **ecosystem-level** target (no PFT breakdown needed);
- plot- or species-resolved biomass/trait → a **PFT-level** target (needs the PFT mapping, 1.2).

The data they have **is** the answer to "what should I calibrate" — the observations determine the targets,
which determine how much model detail (PFT-level or not) they actually need.

**Then classify each dataset by ROLE — calibration vs validation (ask explicitly):**
- **Calibration data** = a goal A2MC should *score and optimize against* → it goes into `targets.yaml`
  and drives the objective.
- **Validation / diagnostic data** = an independent cross-check of ecosystem/soil behavior you do **not**
  fit (you *evaluate* the calibrated model against it) → kept in its **native format**, compared via a
  purpose-built reader/plot script, and **never placed in `targets.yaml`** (it is not scored).

Only calibration data enters `targets.yaml`. A long **time-series** calibration target does not fit the
inline `observations:` list — reference an external data file instead.

**The target grammar is PER MODEL — the four levels below are ELM-FATES's.** `SZPF` is FATES's flattened
size-class x PFT dimension and exists in no other onboarded model; an adapter model (EcoSIM, PFLOTRAN,
ATS) instead writes `variable` / `reduce` / `window_years` keys dispatched through **its own output
registry**, and is validated by a different tool. See the dispatch table in Step 5 — treat that table as
authoritative and this list as the `fates` row of it. For an adapter model, ask the granularity question
in the model's own terms — read the axis from that model's `ModelSpec.grouping_axis` (`pft` for FATES
**and EcoSIM**, `region` for PFLOTRAN and ATS), never infer it from the model's name — and read the legal
names from its registry rather than assuming a PFT axis exists at all.

For **ELM-FATES**, calibration targets span four levels, each with its own key form + extractor:
`PFT<id>_<vartype>` (per-PFT SZPF, e.g. `PFT10_leaf`),
`ECO_<var>` (FATES site scalar — `ECO_gpp`/`ECO_lai`), `SNOW_<var>` (snow site scalar —
`SNOW_snowdp`/`SNOW_h2osno`/`SNOW_fsno`), and `SOIL_<var>_<N>cm` or `_L<n>` (soil profile at a
depth/layer — `SOIL_tsoi_10cm`, `SOIL_h2osoi_L3`). *(Snow-**layer** vars await confirmed ELM `levsno`
output names + extractor support.)* **Validation** data you don't fit is separate — reader scripts, not
`targets.yaml` (see [[reference_calibration_vs_validation_data_taxonomy]]).

### 1.2 — Identify the PFTs (ELM-FATES; ONLY if you have PFT-level targets)

Reach here only when 1.0/1.1 established PFT-level targets. **These are FATES PFTs** — the dynamic,
competing PFTs defined in the base parameter file — **not** ELM's static surfdata PFTs (a separate
system with its own mapping; the surface dataset's PFT fractions don't define the FATES target ids).
Don't ask "which FATES PFT ids" cold — a new user won't know. Ask in **plain ecological terms**: the
dominant vegetation (trees / shrubs / grasses / sedges),
leaf habit (evergreen / deciduous), leaf form (needleleaf / broadleaf), and biome (arctic / boreal /
temperate / tropical). Then **map** those to FATES PFT ids by reading the actual PFT list from the base
parameter file — `get_pft_names_from_file()` (the PFT-inventory command in Step 2 prints every `PFT#id = name`);
never assert the mapping from a name (Calibration Rule #2). These 1-based ids are exactly what `A2MC_PFTS`
holds (each target is then keyed `PFT<id>_<vartype>`, and that id drives the SZPF extraction slice). Confirm
the mapping with the user, and offer to **seed from a similar reference site** (e.g.
`use_cases/ELM-FATES_Kougarok/` for an arctic 3-PFT config). If the user genuinely doesn't know their site's
vegetation, that is a data-collection gap — flag it, don't invent a composition.

### 1A–1D — Detail rounds (ask what the chosen path still needs)

> **1A and 1B are written in FATES's vocabulary** because FATES was the only model when this
> interview was written. For another model, ask the **same questions against that model's own
> knobs** — read them from `models/<model>/spec.py` and its `<model>_template_config.sh` rather
> than translating FATES's. EcoSIM's 1B is the plant-type set and the soil-BGC options; PFLOTRAN's
> is the reaction network and the thermodynamic database. 1.0-1.2, 1C and 1D are already
> model-agnostic and need no translation.

**1A. Where this case runs (recorded here, bound in Step 2).**
- Which model checkout and binary will this case run? Usually the one `a2mc-init` Step 2 built and verified on this machine, or, for a model just onboarded, the one `onboard-model` Steps 0a and 0d located and built; a case may name a different checkout, and Step 2 verifies whichever it is. For ELM-FATES the checkout is the machine config's `A2MC_E3SM_ROOT`.
- Scheduler or workstation? On HPC: the allocation to charge (`A2MC_HPC_ACCOUNT` for a non-CIME model) and where output goes. On a workstation with no scheduler: `A2MC_EXEC_MODE=local` (the EcoSIM backend supports it today), monitored with `arm-local-monitoring`.
- (Online agent only) which AI provider, and is its API key set? The offline agent reasons in the harness and needs neither.

**1B. Model configuration (drives mode-aware retrieval) — resolve from the science goal, not a default.** *(FATES's form; see the note above for another model.)*
- Are you running **FATES**, or ELM without FATES? (`-bgc fates` vs ELM-only.) *For an ecosystem-only GPP goal, PFT competition may not be needed — a `nocomp` or simpler config (or ELM-SP) can be the right, cheaper choice; don't default to full competition.*
- If FATES: **carbon-only or nutrient-enabled?** → PARTEH mode 1 vs 2 (CNP). `A2MC_FATES_PARTEH_MODE`.
- If nutrient-enabled: **ECA or RD**? (`-nutrient_comp_pathway eca|rd`.) Soil decomposition (CENTURY vs CTC)?
- Any Tier-2 FATES features on (SPITFIRE fire, plant hydraulics, logging, no-comp)? Default off.
- **Spin-up protocol** — accelerated-decomposition (ADSP) + regular spin-up (RGSP) years before the transient run, and the supplement-N/P flags per phase (`A2MC_{ADSP,RGSP,TRANS}_{SUPLPHOS,SUPLNITRO}`, defaults in `a2mc_config.sh`). **This is independent of the target granularity** — even an ecosystem-level GPP goal usually needs spin-up to equilibrate C/N/P and soil pools; ask the user how much (or whether) to spin up rather than inferring it from the goal. An expert may prescribe the exact protocol; a novice gets the default + why it matters.

**1C. Site.**
- Site name (used in case names + paths), latitude, longitude; surface + domain data files (NetCDF paths).
- **PFTs — only if 1.0/1.1 established PFT-level targets** (the mapping from 1.2). Ecosystem-only goals skip this.

**1D. Calibration targets + parameters.** (Mostly captured by 1.0/1.1 already; formalize here.)
- Each target as either a **`PFT<id>_<vartype>`** key (PFT-level) or an **ecosystem-level** target — with value, units, uncertainty, and the measurement year/month. Only values the user gave you.
- **Target variant — classify each (from the 1.1 data inventory), it decides the `targets.yaml` shape + a sensible metric:**
  - **Snapshot** (one value at one time) → scalar `observed` + `uncertainty` at `time_year`/`time_month`; metric `relative_error` (default).
  - **Time series / several time snapshots** (a variable at N times) → **one** target with an `observations:` list (one point per time, each with its own value/uncertainty/window); metric a series metric (`nrmse` / `nse` / `kge` — skill scores need ≥2 points). Both scoring paths score it on ALL points.
  - **Several stocks / variables** (leaf, fine-root, AGB, GPP…) → **separate** targets, one per variable; do not merge them.
- **Cost function** (the calibration objective — built from these targets; most users take the defaults). Ask, or default: the **error metric** per target (per the variant above), how targets **aggregate** into one composite (`rmsre` default; `weighted_mean` if some targets matter more), any per-target **weight**, and the **satisfied tolerance** (±20% default). Mixing very different stocks under one composite? use a **comparable-scale metric** per target (relative / normalized / a skill score) + weights so no single target dominates — the FATES validator `validate_targets_config.py` WARNs when `rmsre` mixes relative + absolute metrics (the adapter validator `validate_model_targets.py` has its own rule set). These become a `cost_config` block + per-target `cost_method`/`weight` in `targets.yaml` (Step 4); screening (`optimize_function.py`) and single-case eval (`evaluate_case.py`, with `year_start`) both honor them.
- **Do you have an initial list of parameters to calibrate** (a `FATES_Parameter_List*.txt` + SALib problem file), with bounds? Three cases: **(a)** vetted list → use it (still coverage-check it in Step 4b); **(b)** rough/partial → we vet + complete it; **(c)** none → **the agent builds one from the mechanisms** in Step 4b. Never default to copying the Kougarok 162-parameter set — its *values* and its parameter *set* are Kougarok-specific.

> **Arctic/tundra site?** Offer to seed from `use_cases/ELM-FATES_Kougarok/` instead of the bare `TEMPLATE/` — a working 3-PFT arctic config, a 162-parameter list, and transferable knowledge (Allocation Paradox, P-limitation). Exact parameter *values* never transfer; the structure does.

### Synthesize before you build — do not write config yet

The interview answers (both paths) feed a single **research plan**, not the config files directly. Step 2
verifies the model install this case will run, Step 3 gives the case a directory, and Step 4 drafts the plan
into it and gets the user to **confirm** it — that confirmation is the gate before you create the case memory
and propagate answers into config. Do **not** fill values into the site config or `targets.yaml` until the plan
is confirmed; the template copy Step 3 makes, with its `<PLACEHOLDER>`s, is expected and is not a write.

## Step 2 — Bind this case to a verified model install

A non-CIME case chooses its own checkout and binary, so the check that the checkout matches a registered
knowledge profile belongs to the case, not only to the clone: a second case can point at a different
checkout that nothing has checked. Run it for **every** case, against the checkout this case will use:

```bash
# ELM / ELM-FATES
python scripts/rag_match.py --model-path "$A2MC_E3SM_ROOT"
# EcoSIM, PFLOTRAN, ATS
python tools/model_preflight.py --model <model> --checkout <this case's checkout> --param-file <base param file>
```

| `model_preflight` verdict | exit | what to do |
|---|---|---|
| match | 0 | record the matched profile for the research plan |
| **DRIFT** | 3 | the model is onboarded and this commit is not the registered one. **Proceed, and say so**: the plan records the checkout's commit and the profile the agent will reason with; rebuild the profile (`rebuild-rag`, or `ecosim-version-drift` for EcoSIM) only if the user's source differs in the mechanisms being calibrated |
| NO MILESTONE | 2 | the model's onboarding stopped before its milestone: resume `onboard-model` |
| CANNOT VERIFY | 1 | no version was read: fix the path, or get and build the model first (`a2mc-init` Step 2). A model installed without its git metadata (a tarball, a conda or spack install, a copied binary) can never be read: record its version by hand in the plan and treat it as drift |

**How far is the drift?** A checkout a few commits from the registered one usually reasons fine on the
registered profile. One far from it (another major version, or hundreds of commits) almost certainly
differs in the mechanisms being calibrated: say so in the plan, and rebuild the profile before the first
round rather than after it.

**The binary.** A non-CIME case runs a binary, and it must be an **archived** one, not the live build
path: a queued job resolves its executable at run time, and a rebuild in the shared tree silently swaps
it ([[feedback_bind_runs_to_archived_binaries]]). Archive a fresh build right after building it, while
the tree still matches:

```bash
tools/model_archive_build.sh --tree <checkout> --binary <built executable> --archive <archive root>
# the copy lands in <archive root>/<branch>_<shortsha>/; bind the site config to THAT path
```

**Check the case's inputs against the binary.** A binary and an input file from different commits can
disagree about which variables the input carries, which aborts mid-read after a wasted submission:

```bash
python tools/model_check_input_compat.py --model <model> --checkout <checkout> --param-file <base param file>
```

Take the output location and the HPC account from interview round 1A, which asks for them, and name the variables they bind to: `A2MC_OUTPUT_ROOT` (ATS: `A2MC_CASE_ROOT`) and `A2MC_HPC_ACCOUNT`. If 1A left either open, ask now. Output can grow large, so a scratch or project space, not a home directory. Record those with the checkout and the archived binary for Step 4(b); nothing is
written yet. (ELM-FATES builds per case under CIME and has no shared binary to archive.)

**ELM-FATES only: the PFT inventory.** Read the PFT list from the base parameter file this case will run,
never from a name or a hardcoded count ([[feedback_derive_pft_count_never_hardcode]]):

```bash
python -c "from tools.fates_utils import get_pft_names_from_file as g; \
  d=g('$A2MC_E3SM_ROOT/components/elm/src/external_models/fates/parameter_files/fates_params_default.json'); \
  print(f'{len(d)} PFTs total'); [print(f'  PFT#{i} = {n}') for i,n in d.items()]"
```

Use the case's own base file if it has one; the path above is the checkout's default (JSON from FATES
api 43; older checkouts ship `.cdl`/`.nc`). The count and the `PFT#id = name` list are what 1.2 maps the
user's vegetation to and what `A2MC_PFTS` holds. An adapter model reports its own grouping axis in
`model_preflight`'s output (`subgrid:` line) when given `--param-file`.

## Step 3 — Give the case a directory

Scaffold the case from its model's template **before** the plan, because the plan is written into the
case. The scaffold copies template files with their `<PLACEHOLDER>`s and nothing else, so it records no
decision; filling values waits for GATE 1 in Step 4.

```bash
python tools/create_use_case.py --list                       # model keys, prefixes, and each one's template
python tools/create_use_case.py --model <model> --case <Case> --dry-run
python tools/create_use_case.py --model <model> --case <Case>
```

`<model>` is the registry key as `--list` prints it (`ats` · `ecosim` · `fates` · `pflotran` today);
`<Case>` is the site, project or scenario. The directory is `use_cases/<Prefix>_<Case>/`, where the
prefix is read from that adapter's own `ModelSpec.display_name`, so it cannot drift from the model's
identity. The seed is the model's own `use_cases/<Prefix>_template/`, copied verbatim, with its site
config renamed to `config/<model>_<case>_config.sh`.

**It refuses rather than half-succeeding.** An existing case is never overwritten and there is no
`--force`; a model with no case template routes you to `onboard-model`; an unsafe case name, a missing
seed, or any failed step leaves nothing on disk. All exit 1. **Never scaffold by hand with `cp -r`**: it
keeps the template's config name, so the site config the rest of setup sources does not exist.

**Seeding from a finished case** instead of the template: `--seed <CaseDir>`, for example
`--seed ELM-FATES_Kougarok` for an arctic ELM-FATES site. Only a case present in **this** clone can seed:
the public `A2MC` ships no case study, so there a seed is a case you were given or made yourself. The
script renames the seed's config to yours and keeps its values, which are the seed site's, so edit them;
only the structure transfers.

## Step 4 — Draft the research plan, confirm, then populate the use case

**Draft the research plan — it is the build gate.** Synthesize the interview (Step 1) and the model
install Step 2 verified into a single **research plan**, write it into the case Step 3 created, and get
the user to confirm it *before* any value goes into config.

Write `$DEST/research_plan.md` — a plain-language
synthesis a domain reader can confirm without project context (the report discipline,
`feedback_report_writing_self_contained`):

- **Science goal + question** and the **target granularity** (ecosystem-level vs PFT-level) with the reason;
- **Calibration + validation targets** — each as its `PFT<id>_<vartype>` or ecosystem-level key, with value,
  units, uncertainty, source, year/month, **and its variant** (snapshot / time-series / several-snapshots —
  the latter two as an `observations:` list; several stocks = several targets) (only values the user gave you — mark gaps `TODO`);
- **Cost function** — the error metric per target (matched to the variant) + how they aggregate into the
  composite + any weights + the satisfied tolerance (the calibration objective; defaults: `relative_error` + `rmsre` + ±20%);
- **Model configuration** — FATES/ELM, PARTEH mode, ECA/RD, soil decomp, Tier-2 flags, and the **matched
  milestone** (Step 2);
- **Site** — name, lat/lon, data files; **PFTs** (mapping from 1.2) or "ecosystem-only — PFTs not required";
- **Parameter approach** — bring the user's list / vet-and-complete / build from mechanisms (Step 4b), with
  the candidate mechanisms per target if known;
- **Ensemble design + compute cost** — the intended **sampling scheme** (Morris / Sobol / LHS), the
  resulting **ensemble size**, and a **core-hour + wall-clock estimate**, with the trade-off stated up
  front (full detail + the agreement gate are in Step 4b). Even at plan stage, flag if the chosen scheme
  implies a very large, expensive ensemble;
- **Seed** (`TEMPLATE` vs `Kougarok`) and the **open questions / data gaps** to resolve before Phase 0.

**Present it and ask the user to confirm or correct — this is GATE 1, and it is ITERATIVE.** Answer every
question the user raises and fold in every requested change, then **re-present the revised plan**. **Do
not advance past this gate (to config, or to the Step-4b parameter list) while any question or request is
unresolved** — keep looping until the user *explicitly approves* the plan. Only then build config.

**On confirmation — (a) record the case memory, then (b) propagate the plan into config.**

**(a) Persist the intent** so the next session + the calibration agent inherit *why* the setup looks as it
does, not just the files:
- the **site config** mode env vars — the structural record (env vars = intent, `feedback_env_vars_are_intent_case_dir_is_truth`);
- a **`calibration-log`** session log under `use_cases/$CASE_DIR/memory/logs/` (science goal, target granularity,
  data sources, PFT mapping or skip decision, seed) — anchored to the confirmed `research_plan.md`;
- optionally seed initial **site knowledge** via `inject-knowledge` — only *verified* facts the user gave you
  (a measured target value, a known site trait), never a guess (the evidence gate, `docs/33`).

**(b) Propagate the confirmed plan into the config files** (all under `$DEST`, defined under §Naming):

1. **Site config** `use_cases/$CASE_DIR/config/<model>_<case>_config.sh`. Replace every `<PLACEHOLDER>`; `python3 tools/check_stage_ready.py --case $CASE_DIR` fails while any remain. **Every model:** the site identity (name, lat/lon), the data it reads, and the model install Step 2 bound. **ELM-FATES** (`fates_template_config.sh` sections): §1 site identity, §2 domain/surface/forcing data, §3 `A2MC_PFTS` (the 1-based **FATES** PFT ids of the calibrated PFTs), §6 the mode env vars (`A2MC_ELM_OPTIONS`, `A2MC_FATES_PARTEH_MODE`, Tier-2 flags) — these make retrieval configuration-aware, so set them to the user's actual run, not the template defaults. **EcoSIM, PFLOTRAN, ATS:** `A2MC_MODEL_PATH`, the archived binary (`A2MC_ECOSIM_BINARY` / `A2MC_PFLOTRAN_BINARY` / `A2MC_ATS_EXE`), `A2MC_HPC_ACCOUNT` and `A2MC_OUTPUT_ROOT` (or `A2MC_EXEC_MODE=local` on a workstation), plus the base parameter files and run-control inputs the template names. Write a setting the template writes as a plain `export` by editing the file: exporting it in your shell first does not win.
2. **Validation targets + cost function** `use_cases/$CASE_DIR/validation/targets.yaml` — one entry per target. **For ELM-FATES a key is one of the four forms in 1.1** (`PFT<id>_<vartype>`, `ECO_<var>`, `SNOW_<var>`, `SOIL_<var>_<N>cm`/`_L<n>`); a key in none of them does not resolve and is dropped at runtime, which the FATES validator reports as an ERROR. **Only `PFT<id>_<vartype>` keys are scored in FATES Phase-2 ensemble screening today**: the site-level forms evaluate in single-case evaluation but screen as NaN with no warning (audit `20260923b`, F59; the fix is in FATES-shared screening code), so a round that depends on a site-level target must score it in Phase 5, and the plan should say so. Snapshot targets carry a scalar `observed` + `uncertainty` matched at `time_year`/`time_month`; **time-series / several-snapshot** targets use an `observations:` list (one point per time). Several stocks → several targets. Only enter values the user gave you. **The cost function lives here too:** a top-level `cost_config:` block (`error_method`, `aggregation_method`) + optional per-target `cost_method` / `weight` (defaults: `relative_error` + `rmsre` + weight 1.0) — **match each `cost_method` to the variant** (a series may use `nse`/`kge`/`nrmse`; a snapshot cannot — skill scores need ≥2 points). Validate with the validator **for your model**: FATES → `tools/validate_targets_config.py` (checks the keys, the `cost_config` metrics against the valid sets, and warns on mixing relative + absolute metrics under `rmsre`); any other model → `tools/validate_model_targets.py --model <m> --targets <path>`, which checks `variable` against that model's output registry and understands `reduce`/`window_years`. **The `PFT<id>_<vartype>` key rule in this item is FATES's**; an adapter case names targets for the quantity (`GPP`, `outflow_Ca`) and should also carry a top-level `model:` key so the file declares itself. Format + examples: the seed `targets.yaml` header and `docs/a2mc_reference/user_guide.md` §4.5.
3. **Parameters** `use_cases/$CASE_DIR/parameters/` — drop in the user's list, or build one in **Step 4b** (below). The list defines the entire Morris search space, so it is the highest-leverage design choice here — do not shortcut it by copying Kougarok's set.
3c. **Canonical script TEMPLATES** `use_cases/$CASE_DIR/scripts/` — the directory exists from the scaffold. **Copy a template in only if one exists** (the model's template case, or a comparable case in this clone); the shipped `*_template/scripts/` hold only a README today, so on a fresh public clone there is usually nothing to copy, and then the first use of a script is written in its phase's `phase_results/{stem}/` and promoted here on its second use (the rule under §"The three script tiers"). **Do this at onboarding, not mid-round.** The round's phases will each copy a template into their own `phase_results/{stem}/` and adapt it there; the tier only works if it exists before the first phase needs it, and a case that reaches Phase 3 without it produces the duplication measured below instead. Seed at minimum the **sim-vs-obs time-series template** covering every scored target, since `phase2-screening` Step 1b, `phase3-diagnosis` and `phase6-refinement` Step 1b all require that figure and would otherwise each write their own. See §"The three script tiers" below for what belongs in each tier.

3b. **Round record** `use_cases/$CASE_DIR/config/calibration_rounds.yaml` — **generate this LAST, after the parameter list exists (Step 4b)**: it derives `A2MC_N_PARAMS` / ensemble size / the SALib-problem path from the parameter list, so generating it before Step 4b reads an incomplete config (and Step 5's `check_calibration_rounds` then fails). **Do NOT hand-author it** (it duplicates the configs and silently drifts). Once the param list is built, source the site config and run **the generator for your model** — they are not interchangeable, and the FATES one run on an adapter case merges FATES keys into the template's record and leaves its placeholders in place (F63): **ELM-FATES** `python tools/generate_calibration_rounds.py --round 1 --write`, then `python tools/check_calibration_rounds.py`; **EcoSIM, PFLOTRAN, ATS** `python scripts/generate_adapter_calibration_rounds.py --round 1 --write`, then `python scripts/check_adapter_calibration_rounds.py --round 1`. Both fill params/ensemble/paths/targets/protocol/milestone/commits from the environment and leave `rationale`/`changes_from_previous`/`patches` as `TODO`; fill those by hand before the check.


## Step 4b — Build (or vet) the parameter list from the mechanisms

> **Write it in the CANONICAL format, and CONVERT a user-supplied list into it.** The canonical
> form is EcoSIM's (PI, 2026-08-02): `name` + `pft` + bound columns carrying the `_bound` suffix,
> plus `default`, `description` and `bound_source`. Schema + worked rows:
> `use_cases/TEMPLATE/parameters/parameter_list_template.csv`, which ships everywhere. (In the
> dev repo, `EcoSIM_BioCON`'s list shows every column filled and `PFLOTRAN_miniLEO`'s the core
> ones; neither case ships on the public line.)
>
> **Intake conversion is this skill's job.** A user arriving with a list in another dialect gets it
> converted here, not carried through — two dialects downstream is what the canonical decision
> removes. Preserve `bound_source` when converting, and where the source list has none, mark the
> bounds `provisional` rather than leaving the column blank: a blank reads as "not recorded", which
> is indistinguishable from "published range" to the next reader
> ([[reference_param_bounds_sourcing_pipeline]]).
>
> **The axis set is EXTENSIBLE.** `pft` and `organ` are the basic axes and both ship in the
> template; add a column for any further axis this case needs (`mineral`, a microbial guild, a
> chemical species) rather than overloading `pft`. The id builders consume one axis today
> (`models/base.py:199`), so a non-PFT axis sits in `pft` as a documented stopgap — declare the
> real column anyway.
>
> **`bound_source` uses a controlled vocabulary**, and converting a list is exactly when it gets
> applied: `measured:` (this project's own data, naming the campaign + statistic), `literature:`
> (citation AND a resolvable DOI), `database:` (TRY / FRED / FLUXNET, naming the record + DOI),
> `prior_round:`, or `provisional:` with the basis stated.
>
> **Two file-format traps, both verified 2026-08-03.** Name the bound columns with the `_bound`
> suffix — the bare form is matched on a whitespace split, so in a comma-separated header it never
> matches and the file fails to parse. And no commas in any free-text cell: there is no quoting
> step, so one comma shifts every later column.
>
> **FATES's live 168-parameter list stays in its legacy dialect** and must not be rewritten under a
> running round. The loader-side compat shim (`tools/param_spec.py`) is separate, tracked work.

> **★ FIRST — enumerate the model's PARAMETER-BEARING INPUTS, before writing a single row.** Two
> lists exist and they are NOT the same:
>
> 1. **What A2MC wires** — `models/<model>/spec.py` is the authority. `secondary_namelist_var` and
>    `tertiary_namelist_var` and `quaternary_namelist_var` name the extra slots, set per case through
>    `A2MC_SECONDARY_PARAM_FILE` / `A2MC_BASE_PARAM_FILE_3`. FATES uses one slot; EcoSIM three.
> 2. **What the MODEL actually reads** — the model adapter's `README.md` surfaces table, or the
>    input files its runfile/deck names. **This list is usually longer**, and the difference is
>    invisible from `spec.py` alone.
>
> **Do not infer either list from the case config** — that shows only what *this* case happens to
> wire, a subset of a subset.
>
> The gap is not hypothetical. EcoSIM's `grid_file_in` holds ~114 soil variables including `CORGC`,
> and BioCON R2 found scaling it the decisive soil-respiration lever — yet it has **no A2MC slot**
> and had to be perturbed with purpose-built probe scripts. A list scoped to the wired slots would
> have silently excluded the winning parameter ([[reference_ecosim_parameter_surfaces]]).
>
> Then **state in the list which surfaces it covers and which it does not**, because a list that
> silently spans one of four surfaces reads as complete. A surface can be unreachable for a real
> reason: EcoSIM's microbial file is *optional in the model*, and when its namelist entry is blank
> the run uses compiled-in Fortran constants, so there is no file for A2MC to perturb and that whole
> process is uncalibratable until the file is wired — with nothing in the run to hint at it
> ([[reference_ecosim_parameter_surfaces]]). Wiring a surface mid-campaign can also move the
> baseline, so it is a new-round decision, not an edit.

The parameter list is the single most consequential decision in setup: it *is* the Morris search space. A list that omits the parameters that actually drive a target guarantees that target can never calibrate; a list padded with irrelevant parameters wastes the ensemble. So when the user has no list (interview D case c), or a rough one (case b), **build/complete it by studying the mechanisms — never by guessing from parameter names** (Calibration Rule #2). When the user has a vetted list (case a), still run the coverage check at the end.

**Work target-by-target.** For each calibration target (a `PFT<id>_<vartype>`, e.g. `PFT10_leaf`), ask: which FATES mechanisms produce this output, and which parameters drive those mechanisms? Answer from the knowledge system, not intuition. RAG ops need the Python-3.10 interpreter (see `docs/a2mc_reference/user_guide.md` §6 / the RAG reference for the exact binary).

1. **Query the knowledge system** for each target output + PFT, filtered to the active mode:
   ```python
   from rag import HybridRetriever
   r = HybridRetriever(auto_build=False)
   ctx = r.get_calibration_context(
       outputs=["FATES_LEAFC_SZPF"], pft=10, config_mode=None)  # params/mechanisms/docs for this target
   info = r.get_parameter_info("fates_leaf_slatop")             # confirm a candidate's effect + direction
   mech = r.get_mechanism_info("carbon_allocation")             # mechanism → parameters it exposes
   ```
   Cross-read the **curated overlay** `rag/data/curated_relationships_<profile>.yaml` (the human-vetted parameter→mechanism→output map for the matched milestone) — it is the source of truth for which parameters matter. For **nutrient-enabled** runs, START at the CNP calibration guide in the active milestone's wiki (`docs/fates-knowledge-base/fates-codebase-wiki-<commit>/advanced/cnp_calibration_guide.md`) for PID gains, `vmax`, stoichiometry, and retranslocation parameters.

   **For a non-ELM onboarded model (e.g. EcoSIM), dispatch through the adapter instead of the FATES paths above** (roadmap L3.2): the parameter→mechanism→output map is the model's own **curated seed** (`models/<name>/curated_seed.yaml`, its `parameters:` calibratable subset), not `curated_relationships_<profile>.yaml`; and the param list + bounds are generated by the model's own generator — for EcoSIM, `python scripts/generate_ecosim_bounds.py` produces a `parse_param_list`-compatible CSV with default-anchored provisional bounds, which you then refine (the `literature-review` skill's parameter-bounds mode is the tool). The "never invent a bound" rule (item 3 below) applies identically. **Round record (Step 4 item 3b) for a non-ELM model:** use the adapter analog `python scripts/generate_adapter_calibration_rounds.py --round N --write` then `python scripts/check_adapter_calibration_rounds.py --round N` (the FATES `generate_/check_calibration_rounds.py` are FATES-config-coupled). The adapter version DERIVES the round block from the two config files + the param-list CSV + `targets.yaml` + git in `A2MC_MODEL_PATH`, with a model-dispatched `protocol` (e.g. EcoSIM `single_continuous`, not FATES ADSP/RGSP/TRANS) and `<model>_source` block, and reads `status` from `workflow_state_offline`. The site config must set the REAL `A2MC_N_PARAMS`/`A2MC_N_TRAJECTORIES` (they override the generic a2mc_noncime defaults). Same rule against hand-editing the derived fields.
2. **Pull prior experience** from Adaptive Memory, from **this model's** store and never another model's: `memory/gained_knowledge/` is the **FATES** store (unprefixed only because FATES predates the per-model layout), and an adapter model's is `memory/<model>/gained_knowledge/`; `tools/model_knowledge_store.py` resolves it and has no cross-model fallback (F09). Read its `parameters.json` (known bounds/sensitivities) and `discoveries.json`, and, for a similar site in this clone, the reference site's `use_cases/<ref>/memory/gained_knowledge/{parameters,discoveries,failed_approaches}.json` (which parameters were sensitive, which pitfalls to avoid). Mechanistic insight transfers across sites; exact values do not.
3. **Assemble each entry** with: FATES parameter name, the group it applies to in its own column (`name` holds only the official parameter name, `pft` the group id: `alloc_storage_cushion` + `pft=10`, never `alloc_storage_cushion_10`, which is the legacy FATES Morris shorthand; see `docs/a2mc_reference/fates_data_reference.md`), the target/mechanism it addresses, and **bounds**. Anchor each bound to the FATES default parameter-file value plus a defensible ± range from the knowledge base / literature / the reference list. **Never invent a bound** — an unfounded range silently distorts the whole sensitivity analysis. If a bound is genuinely unknown, mark it `TODO` and flag it to the user.
4. **Right-size, don't pad.** Morris cost = `n_trajectories × (n_params + 1)`; a broad list is affordable *because Phase 1 sensitivity prunes it* — but every parameter must trace to a target through a named mechanism. No "might as well include it." Flag targets with no driving parameter (a coverage gap) and parameters with no target link (drop them).
5. **Present the proposed list for review before writing — this is GATE 2, and it is ITERATIVE.** Per parameter: the target it serves, the mechanism, the source citation, and the bound rationale. Answer every question and fold in every requested add / drop / bound change, **re-presenting until the user agrees** (like curated-knowledge writes — do not write while a request is open). On agreement, write the parameter list to `use_cases/$CASE_DIR/parameters/` in the canonical format above and point `A2MC_PARAM_LIST_FILE` at it. **Do not hand-write the SALib problem file**: Phase 0's sampler generates it from the list (`create_parameter_sample.py` for ELM-FATES, `scripts/create_adapter_parameter_sample.py` otherwise, both writing to `A2MC_SALIB_PROBLEM_FILE`), and the Step 5 gate reports it N/A until then.

6. **Agree on the ensemble-simulation design (still GATE 2) — surface the trade-offs, then follow the user's choice.** With the parameter count now fixed, confirm the **sampling scheme** (`A2MC_SAMPLING_SCHEME`) + resulting **ensemble size** and **compute cost** with the user *before* writing the config / round record. Compute and **SHOW the numbers per option** so the choice is informed (A2MC's `calculate_ensemble_size()` in `a2mc_config.sh` gives the exact count per scheme):
   - **Morris** (default) — `n_traj × (n_params+1)` sims: a cheap sensitivity **screening** (μ*). e.g. `30×(171+1) = 5160`.
   - **Sobol** — `N × (2·n_params+2)` sims (SALib Saltelli, `N`≈500–1024): rigorous first + total-order variance sensitivity, but **often 10–100× more simulations** → far more core-hours, much longer wall-clock, heavier queue pressure. e.g. `512×(2·171+2) = 176,128`.
   - **LHS** — `N` space-filling samples (user-set `N`): cheaper than Sobol, no sensitivity indices.
   Multiply the ensemble size by the per-case core-hours (ADSP + RGSP + TRANS) for a **core-hour + wall-clock estimate**, and state it plainly (queue/walltime reality too). **Recommend** — Morris for screening; Sobol only when full variance decomposition is the goal and the compute budget genuinely allows it. **But if the user chooses the expensive path (e.g. Sobol), FOLLOW it — inform of the trade-off, never override an explicit choice** (the defer-to-the-user rule, `a2mc-init` Step 0). Iterate until the user agrees; only then set `A2MC_SAMPLING_SCHEME` / `A2MC_N_TRAJECTORIES` and generate the round record.

**If the user brought a list (case a/b):** run steps 1–2 as a *coverage check* — confirm every target has ≥1 driving parameter in the list and flag any parameter with no mechanistic tie to a target. Report gaps; do not silently rewrite their list.

**Now the parameter list exists → generate the round record (Step 4 item 3b)** with the generator for your model named there (it derives from the parameter count you just wrote) → fill the TODO narrative → run the matching checker. That is the last prep artifact; then run the Step 5 gate.


## The three script tiers — template, instance, library

**Added 2026-08-22 (PI).** A script has three possible homes and they are not interchangeable. Getting this wrong produced, measured on one site: **7 script names duplicated across `phase_results/` folders, all 7 byte-identical**, every one a Phase-5 script copied verbatim into its Phase-6 folder because there was nowhere else for it to live.

| tier | what lives there | canonical for | when |
|---|---|---|---|
| `use_cases/{Model}_{Case}/scripts/` | the **canonical script TEMPLATE** | the shape, interface and conventions REUSED across the round's phases | seeded at **onboarding** (item 3c); a script's **second** use is the trigger to template it |
| `use_cases/{Model}_{Case}/memory/phase_results/{stem}/` | the **canonical script** for that figure, beside its caption, data and notes | *that* figure, in *that* phase | copied from the template and **adapted** for the phase's specific purpose |
| `tools/` · `phases/phase3_diagnosis/` | the generalized, site-agnostic utility | every site and round | round-close promotion, human-gated |

**This does NOT conflict with "ONE canonical script per figure, never two copies."** The vocabulary distinguishes them: the **canonical script** always stays with its figures, and the **canonical script TEMPLATE** stays in `scripts/`. They are different artifacts with different jobs, so a template plus its per-phase adaptations is not the duplicate that rule forbids. What the rule still forbids is one figure with two scripts that drift.

**The trigger is the SECOND use.** The first use writes the script in `{stem}/`. The second time it is needed, copy it to `scripts/` as the template, then copy it back into the new `{stem}/` and adapt. Not rule-of-three: every duplicate group measured was exactly two.

**Round close RECORDS, it does not auto-promote.** A script reused across one site's round is evidence it is reusable *for that case*, not that it generalizes across models. The round summary lists what is in `scripts/` and what it was used for; promotion to `tools/` stays a separate human-gated decision.

## Step 5 — Preflight: is the setup ready for Phase 0? (goal-conditional gate)

```bash
source use_cases/$CASE_DIR/config/<model>_<case>_config.sh   # auto-sources its machine config (v2.306)
print_config                        # ELM-FATES only (defined by a2mc_config.sh): paths/PFTs/mode
python tools/describe_mode.py       # ELM-FATES only: the mode A2MC will actually use
python tools/check_setup_ready.py   # the aggregate, goal-conditional readiness gate
```

> **If an AGENT is running this, join the `source` to the command that needs it** — `source … && <command>`. A harness gives each shell call a fresh process, so a config sourced on its own is gone by the next call, and the script then reports its variables unset as though nothing had been sourced. A human at a terminal is unaffected. Full statement: `AGENTS.md` §"Source the config and run in the SAME command".


`check_setup_ready.py` is the single **goal-conditional** readiness gate. It runs the *universal*
checks — model path + matched milestone, **site config overrides the machine config**, `targets.yaml`
valid **AND every target mapped to a model output variable with a cost function established**,
parameter list present, `calibration_rounds.yaml` present + consistent with the config — and reports
**`N/A` (never `✗`) for checks that don't apply to this user's goal**: PFT inventory only for
PFT-level targets (an ecosystem/flux goal skips it), FATES base file + RAG milestone only when FATES
is on, and the spin-up **protocol is reported, not required** (spin-up is the user's decision, set in
config — independent of the target granularity). It wraps the round-record checker and the
targets validator, **both dispatched by model** (below), so a green run means those pass too. Exit 0 = ready
for Phase 0; every `✗` must be resolved first. Matching the checkout to a milestone is Step 2's job:
`scripts/rag_match.py` for ELM-FATES (how-to: `docs/a2mc_reference/version_association_howto.md`),
`tools/model_preflight.py` for every other model.

> **★ The targets check is DISPATCHED BY MODEL — there are two validators and they are not
> interchangeable.** `$A2MC_MODEL` (default `fates`) selects:
>
> | model | validator | target grammar it understands |
> |---|---|---|
> | `fates` | `tools/validate_targets_config.py` | `PFT<id>_<vartype>` keys, SZPF resolution, `time_year`/`time_month` anchors |
> | anything else | `tools/validate_model_targets.py --model <m>` | `variable` / `reduce` / `window_years` / `window`, dispatched to the model's own output registry |
>
> **Run the one for your model directly when the gate says `✗`** — the gate only reports pass/fail.
> The FATES validator now **refuses** an adapter model's file and names the right tool, so pointing
> the wrong one at a case is caught rather than answered with nonsense.
>
> **Why this is called out rather than left as plumbing:** until 2026-08-18 the gate ran the FATES
> validator unconditionally, and two of its rules cannot be satisfied by an adapter target by
> construction — so it emitted exactly `2 × n_targets` spurious errors and **could never exit 0 for
> EcoSIM, PFLOTRAN or ATS** (measured: BioCON 6, Lusignan 6, PFLOTRAN_miniLEO 22). If you are
> reading an older case's notes and see this step failing on targets for a non-FATES model, that is
> the bug, not your case. Audit `20260816b`, fix `20260818a`.
>
> **A `warnings only` result does NOT block Phase 0** for an adapter model — the two validators
> report warnings through different exit codes and the gate normalises them. Warnings are surfaced
> in the gate line; read them, but they are not a `✗`.
>
> **Give `targets.yaml` a top-level `model:` key** (`model: ecosim`). It lets the file declare
> itself, so the right validator is chosen even with nothing sourced. `EcoSIM_Lusignan` and
> `PFLOTRAN_miniLEO` carry it; `EcoSIM_BioCON` does not and is identified from `$A2MC_MODEL` alone.


## Step 6 — Hand off to Phase 0

Setup is done. Route to **`phase0-design`** to sample the parameter space and submit the ensemble. From here on the standard cold-start flow applies: `onboard-session` on the next session, and once the ensemble is in flight `arm-hpc-monitoring` on a scheduler or `arm-local-monitoring` on a workstation (`A2MC_EXEC_MODE=local`). The model's runbook skill (`ecosim-run-workflow`, `pflotran-run-workflow`, `ats-run-workflow`, or `offline-testing-workflow` for ELM-FATES) covers every run after this one.

> **Or start a driven run.** To go straight from setup-complete into a run that drives itself to the calibration goal (rather than a bare Phase-0 hand-off), invoke **`calibration-goal`** — the run-to-convergence driver loops the 7-phase workflow to CONVERGED, pausing only at the human gates.

The setup's session log was written in Step 4(a), when the plan was confirmed. If anything changed since (a bound, a target, the ensemble design at GATE 2), add it there with `calibration-log` so the next session inherits the final choices, not the first draft.


## Footguns

- **Raw observation files go in `validation/data/`, never beside `targets.yaml`.** Both roles live
  there — the role is decided by `targets.yaml` naming the file, not by where it sits. Putting a
  diagnostic series where it can be mistaken for a spec is silent and expensive: adding it to
  `targets.yaml` does not error, the round simply starts optimizing toward data you meant only as a
  cross-check, and every downstream artifact still looks correct. Convention + the role table:
  `use_cases/TEMPLATE/validation/data/README.md`. **A long time series is referenced by path, never
  inlined.** If a target's data path is resolved by code (PFLOTRAN's `observed_series_file:` is),
  moving the file and editing `targets.yaml` must happen in the SAME commit.


- **Template mode defaults left in place** — the seed config ships a FATES+CNP+ECA default; if the user runs carbon-only or ELM-only, retrieval will surface the wrong content until you fix the mode variables (§6 of the FATES template).
- **Bad target keys** — **FATES only**: anything not matching `PFT<id>_<vartype>` is dropped silently; run `validate_targets_config.py`. **An adapter model has a different grammar** (targets named for the quantity, anchored by `window_years`/`window`) — run `validate_model_targets.py --model <m> --targets <path>` instead. Pointing the FATES one at an adapter case used to emit `2 × n_targets` nonsense errors; it now refuses and names the right tool.
- **Fabricated targets/paths** — the single most damaging first-run error. Placeholders marked `TODO`, never invented numbers.
- **Clobbering an existing case** — `create_use_case.py` refuses an existing directory; never work around it with `cp -r`. An existing case is a RESUME of this skill (§Before Step 1), or `onboard-session`'s if it already carries workflow state.
- **Parameter list guessed from names** — the list defines the entire Morris search space; build it from the knowledge system (curated relationships + RAG + CNP guide + Adaptive Memory), not from what a parameter is called (Calibration Rule #2). Fabricated bounds distort the sensitivity analysis — mark unknown bounds `TODO`. Do not reflexively copy the Kougarok 162-parameter set; it is Kougarok-specific.
- **Putting validation data in `targets.yaml`** — `targets.yaml` is **calibration-only** (everything in it is scored/optimized against). Data the user wants as an *independent cross-check* (not fit) — e.g. MODIS GPP/LAI, soil T/moisture profiles for a biomass calibration — is **validation data**: keep it in its native format and compare via a purpose-built script; never add it to `targets.yaml`. Classify calibration vs validation in the 1.1 interview.
- **Over-asking a new user for detail they don't need** — do NOT demand dominant PFTs, per-PFT biomass, or a parameter list when the goal is **ecosystem-level** (e.g. MODIS/tower GPP). Let 1.0 set the granularity first; PFT-level questions (1.2, 1C PFTs) apply *only* to PFT-level targets. Forcing FATES internals on someone who only has an ecosystem flux is the fastest way to stall a first run.
- **Building config before the plan is confirmed** — write `use_cases/$CASE_DIR/research_plan.md` and get the user's confirmation BEFORE filling values into the site config / `targets.yaml` / the parameter list (the template copy Step 3 makes is not a write). The plan is the single human-review artifact; skipping it means the user first sees your interpretation as already-written files, which is far harder to correct. Record the case memory only after the plan is confirmed.
- **Hand-authoring `calibration_rounds.yaml`** — it duplicates values already in the two configs (param count, ensemble size, artifact paths, targets file, protocol, milestone), so a hand-typed round record drifts. Generate it from the sourced config with the generator for your model (Step 4 item 3b: `tools/generate_calibration_rounds.py` for ELM-FATES, `scripts/generate_adapter_calibration_rounds.py` otherwise) and verify with the matching checker; never trust a hand-typed one.
- **Treating a leftover check as a hard failure** — `check_setup_ready.py` is goal-conditional: `N/A` on PFT inventory (ecosystem goal), FATES base file (ELM-only), or an as-yet-ungenerated SALib file is expected, not a blocker. Only `✗` blocks Phase 0.


## Cross-references

- `docs/a2mc_reference/a2mc_init_interview_questionnaire.md` — a ready-to-use branching question script for Step 1 (kept under its original filename)
- `onboard-model` — adds the MODEL; its step 14 delegates case creation here
- `a2mc-init` — once per clone: wiring, name, the model install on this machine (get, build, verify), fork guard and machine config; then routes here
- `phase0-design` — where this hands off
- `calibration-log` · `calibration-discipline` — the logging + habits layer for the round that follows

