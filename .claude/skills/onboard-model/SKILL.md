---
name: onboard-model
visibility: public
category: meta
description: >-
  Take a NEW model (EcoSIM, CLM/CTSM, ATS, TEM, PFLOTRAN, …) from a filled modeler questionnaire
  all the way to a calibration-ready A2MC instance — the full adapter-kit arc: scaffold the
  models/<name>/ adapter package, build the source-grounded knowledge chain (delegating the
  wiki→RAG→curated→validate sub-chain to build-rag-from-scratch), register the version-association
  milestone, and smoke-test the reasoning phases. The single top-level entry point behind the
  adapter-kit promise "import A2MC to calibrate models other than ELM." Use when the user says
  "onboard/add/couple <model> to A2MC", "fork A2MC for my model", "adapt A2MC to <model>", "run the
  adapter kit for <model>", "build an adapter for <model>", or is driving the EcoSIM onboarding.
  NOT for reindexing an existing model's RAG (use rebuild-rag) or the RAG sub-chain alone
  (use build-rag-from-scratch).
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [adapter]
  summary: "Orchestrate the full new-model adapter onboarding; model-agnostic, ships public."
---

# Onboard a New Model into A2MC (the adapter-kit orchestrator)

The **top-level** runbook for coupling A2MC to a model other than ELM-FATES. It sits *above* the
knowledge-layer skills and calls them: `generate-codebase-wiki`, `build-rag-from-scratch`,
`inject-knowledge`, `validate-rag-chain`. What it owns that they don't: the **intake**
(questionnaire → `init_adapter.py`), the **`models/<name>/` adapter package** (spec / parsers /
version / backend / datasets), **adapter conformance** (V4) and **run-template** (V5) validation,
**milestone registration**, and the **execution smoke test**.

Canonical design docs (read for detail, don't re-derive): `docs/17_Multi_Model_Adapter_Architecture_Plan.md` (the
`ModelSpec`/`ModelBackend`/`ModelDataset` contract), `docs/19_Adapter_Kit_Implementation_Plan.md`
(the 14-step CLI spec this skill mirrors). `docs/A2MC_Adapter_Kit_Master_Plan.md` was the
overview and is **SUPERSEDED as of 2026-08-26** — its status dashboard is a 2026-07-06 snapshot,
not a task list; THIS skill is the live version of its five-step pipeline. The `init_adapter.py`
step numbers below are its
`PHASE_A/B/C` maps.

> **Scope boundary.** The kit produces a *defensible v0.1 seed* — a working adapter, a
> source-grounded KB, a calibration-ready RAG. Filling it to production quality for a specific
> model stays the modeler's job. The kit does **not** ship finished EcoSIM/CLM/ATS/TEM adapters.

> **Python for RAG/NetCDF ops (`$PY` below).** On Perlmutter `~/a2mc_env/bin/python` (3.11, with
> `chromadb` and `netCDF4`). On a Mac, a Python 3.10 environment built from `requirements.txt`: a
> Homebrew 3.12 refuses `pip install` under PEP 668.

## Step 0 — what the modeler brings, and what Step 0d produces

> **Definition of done for this stage: `setup-discipline`.** This skill performs the stage; that one
> collects what "finished" means for it, with the executable gate per item. Check it before
> declaring this stage complete.


**Precondition: the clone is wired and the machine config written.** `python3 tools/check_clone_setup.py`
exits 0 (`a2mc-init` Step 1) and the machine config for the model's family is set (`a2mc-init` Step 3).
A user who came here directly does those two steps first; without Step 1 the whole onboarding is
committed with the repo's git hooks off.

**Resuming?** A model whose onboarding stopped part-way (its adapter registers, but it has no
milestone, memory store or run template — ATS on this line) resumes at the first ✗ of
`python3 tools/check_stage_ready.py --model <name>`. Never restart it.

What the modeler brings:
- a **filled questionnaire** (`templates/modeler_questionnaire.yaml`; guide
  `docs/a2mc_reference/modeler_questionnaire.md`). **The agent reads it; no script does.** Check its
  required fields for an `[unsupported]` choice yourself before scaffolding;
- the **model source tree at a known commit** (for a commit-pinned wiki and verifiable citations), or
  where to get it: Step 0a asks where the checkout is, or where to clone it.

What Step 0d **produces** with a user who does not have them yet (not an entry fee):
- a **parameter file** (NetCDF/CDL, JSON, YAML, or namelist) and a **sample output**;
- a **run recipe** that works on this machine (HPC job script or local command).

Strongly recommended: a **user guide + 1–2 application papers** — they make Step 3's mechanism
naming tractable.

If the model shares CIME + NetCDF param files with E3SM (CESM/CTSM), most of this is reuse — the
`*_cime.sh.tmpl` runtemplate + the CDL parsers apply with minimal glue.

## Step 0a — where things go on this machine (ask before anything is cloned or built)

A user who arrives here skipped `a2mc-init` Step 2, which is where a model A2MC already has gets its locations asked. So this skill asks them itself, before Step 0b needs a checkout and Step 0d needs somewhere to build and run. **Ask; never pick a path for the user, and never assume the source is already on disk.**

| ask | used by | becomes, for the first case |
|---|---|---|
| where the model's source checkout is, or where to clone it | Step 0b (`$CHECKOUT`), 0c, step 3 (the wiki's source), step 9 (the milestone's commit) and the pre-flight check after it | `A2MC_MODEL_PATH` in the case's site config (`a2mc_config.sh` for a CIME-family model) |
| where archived copies of built binaries go | Step 0d (`tools/model_archive_build.sh --archive`) | the case's binary variable points into it |
| a run directory for the orientation run: a copy of the model's own sample case, and its output | Step 0d, step 5 (the output surface is read from that output), step 13 (the smoke test's sample files) | recorded in `models/<name>/BUILD.md` as where the sample ran. The case's own output root is a separate question, asked by `onboard-case` round 1A |
| on a cluster, the account a batch orientation run is charged to | Step 0d | `A2MC_HPC_ACCOUNT`, confirmed again by `onboard-case` round 1A |

Source and binaries belong in a project or software space, output in a scratch or project space: never a node-local temp directory, and never a home directory close to its quota, which a build and a sample run can fill. **Run the sample case in a copy**, never inside the source tree's example directory: a run writes its output beside its inputs, and the checkout should hold source, not run output.

Keep the answers as shell variables for the session (`CHECKOUT`, `ARCHIVE_ROOT`, `RUN_DIR`) and write none of them into a tracked machine config: they are this user's, and for a non-CIME model they belong to each case. The hand-off to `onboard-case` passes them on.

## Step 0b — wire the source checkout's fork-only push guard (right after Step 0a, before anything else)

A fresh model checkout's `origin` points at the **upstream project**, so a stray `git push origin`
targets someone else's repo. Contract: memory `feedback_model_source_push_fork_only`. `a2mc-init`
does this for E3SM/FATES by name; **this is the model-generic version, and its absence is why the
ATS checkout sat unguarded through its whole onboarding** (found 2026-07-31 auditing after PFLOTRAN).

Ask the user first — creating a fork under their account is outward-facing. Then:

```bash
git -C "$CHECKOUT" remote add fork <their fork URL>
git -C "$CHECKOUT" remote set-url --push origin DISABLED_push_to_fork_not_upstream
git -C "$CHECKOUT" push origin HEAD --dry-run    # must FAIL
git -C "$CHECKOUT" push fork   HEAD --dry-run    # must SUCCEED
```

Verify **both** directions; a guard you did not test is a guard you do not have. This is **per-clone
git config, never committed** — re-apply on any re-clone.

**A user with no fork or no GitHub account** (which `a2mc-init` accepts) gets the sentinel alone, with
no `fork` remote: `origin` push disabled means a stray push still fails loudly. They cannot push model
source anywhere until they have a fork, which is the point; record that in `models/<name>/README.md`.

Three things vary by model, so decide rather than copy:

- **Fork vs mirror.** `gh repo fork <upstream>` only works when upstream is on GitHub. If it is not
  (PFLOTRAN's upstream is Bitbucket), you get a **mirror**: a plain repo you push to, with no
  "forked from" link and **no ability to PR upstream** — say so explicitly, or someone will plan a
  contribution that cannot happen. Contributing upstream then needs a fork on the *upstream host*.
- **SSH vs HTTPS.** The rule of thumb is SSH, because an HTTPS token without the `workflow` scope is
  refused when history touches `.github/workflows/`. **Check both halves before prescribing it** —
  on 2026-07-31 ATS's history *did* touch `.github/workflows/`, but the active `gh` token already
  carried `workflow` scope, so HTTPS was correct and avoided an SSH-key blocker. `gh auth status`
  shows the scopes.
- **Sentinel string — use `DISABLED_push_to_fork_not_upstream`** (PI decision 2026-07-31; the
  command above already does). It is the message shown in the error and in `git remote -v` to
  whoever trips it, so a consistent one is worth having. EcoSIM, ATS and PFLOTRAN all now carry it;
  **E3SM/FATES keeps its legacy `DISABLED_no_push_to_upstream_*` deliberately** — that guard works
  and re-wiring it buys nothing, so do NOT "fix" it. Standardising applies to *new* onboardings.
  Corollary: a mismatched string is **not** evidence a checkout is unguarded — audit with
  `grep DISABLED_`, never an exact-string match.

**Proportion.** An upstream push nearly always fails on credentials anyway, so the sentinel is
defence-in-depth, not the barrier — it makes the failure immediate and legible and states the intent
in `git remote -v`. Do not oversell it.

Later, `tools/model_preflight.py --checkout <path>` reports this posture on every run (advisory —
it never gates the exit code, since "origin already IS my fork" is a legitimate setup).

## Step 0c — characterize the codebase BEFORE scaffolding

**Read the source tree and answer these seven questions in writing.** They decide the shape of every
later step, and getting one wrong is not a local error — it propagates into the parsers, the wiki,
the seed, the RAG chunks and the targets file. ATS proved the point: it is the first C++,
XML-configured, no-history-tape, no-PFT model, and each of those broke an assumption the kit had
inherited from two Fortran/NetCDF/per-PFT models.

| # | Question | Why it decides later steps | FATES / EcoSIM / ATS |
|---|---|---|---|
| 1 | **Language + build** | sets `spec.source_extensions`, `routine_decl_patterns`, `module_file_pattern`; a C++ tree needs class-oriented wiki sections, not `subroutine` scraping | Fortran / Fortran / **C++** |
| 2 | **How is a parameter ADDRESSED?** | bare name vs path. A path-addressed model needs the **full address as the unique key** — generic leaves recur (`…/value` × 3 in ATS), so leaf-keyed anything silently hits the wrong knob | bare `fates_*` / bare uppercase / **`a/b/c/leaf` path** |
| 3 | **Parameter file format** | drives the parser and every tool that reads it | NetCDF/JSON / NetCDF / **Teuchos XML deck** |
| 4 | **Is there a HISTORY TAPE?** | if not, there is no CDL to scrape and no `*.h0.*.nc` to glob; outputs may be **declared in the input** and absent unless requested | NetCDF h0 / NetCDF h0 / **none — observation `.dat` declared in the deck** |
| 5 | **What is the grouping/multiplicity axis?** | PFT? cohort? material region? none? Decides `grouping_axis`, whether targets need a `pft` slot, and whether parameters repeat | PFT / PFT / **region (no PFT)** |
| 6 | **Run invocation** | CIME vs standalone binary vs python driver; picks the runtemplate variant and the machine config (`a2mc_config.sh` vs `a2mc_noncime_config.sh`) | CIME `case.submit` / `ecosim.x <nml>` / **`ats --xml_file=<deck>`** |
| 7 | **Are there SOURCE-ENFORCED bounds?** | typed readers (`readZeroOneLandCoverParameter`) or guards make some ranges non-negotiable; a naive ±50% band is then rejected **at read time** | — / — / **`[0,1]` on albedo, emissivity** |

Record the answers in the adapter's `README.md` and reflect them in `spec.py`. Two concrete places
they must land, both of which cost real time when missed:

- **`spec.fraction_param_names` / `fraction_categories` / `signed_param_names`** — from Q7. A model
  that declares none gets an unclamped ±frac band from `scripts/model_generate_bounds.py` with **no
  warning**. On ATS this produced emissivity `0.98 → [0.49, 1.47]`, rejected at read time, and
  `surface-relative_permeability 1.0 → [0.5, 1.5]`, unphysical — 3 of 27 bounds unusable, i.e. an
  ensemble that would abort on a third of its cases. Declare fractions **by full address** when the
  set is not category-aligned (ATS `radiation` holds albedo/emissivity *and* Beer's-law
  coefficients, which are not fractions).
- **The deck/case-study distinction** — from Q2 + Q4. If the parameter file IS the case study
  (ATS), then a second site means a second file, and every per-model script must take it as an
  argument rather than hardcode it.

> **Do not infer any of these from names or from another model.** Q4 and Q7 in particular are only
> answerable by reading source or a real input file. `[[feedback_param_description_can_lie_verify_in_source]]`

## Step 0d — orientation run: build it and run its own sample case, WITH the user

**Do this before Step 7 (the curated seed), and preferably before scaffolding.** Step 7 asks you to
write down what matters mechanistically about a model. Doing that for a model **nobody in the room has
ever run** is how an ai-draft seed becomes confidently wrong.

Origin: `20260711a` recorded it as a Next item — *"Get familiar with EcoSIM before running it (PI: 'I
have not run EcoSIM before'). Orientation pass on the model + sample case before executing step 7."* It
never reached this skill, so it evaporated. It is a step, not a note.

### This is work A2MC does, not a precondition A2MC demands

Step 0's preconditions ask for a parameter file, a sample output and a run recipe. **A user new to the
model does not have those yet — they are the OUTPUT of this step, not its entry fee.** Helping a user
stand the model up and learn it is A2MC's job even when they arrive with no knowledge of it (PI,
2026-08-19).

> **This branch has already paid for the opposite stance.** `20260807f` (PFLOTRAN): the item blocking
> everything execution-side — *"a binary at `157a26f7`"* — was recorded as **blocked on the team** on
> 2026-07-31, sat for **a week**, and was then closed **in an afternoon with zero input from the team**
> (`20260807c`) by simply building it. Its lesson: *"we verify numbers; we do not verify ownership."*
> **Never write "you must supply a working model" into a plan.** Try it first.

### The pass

1. **Build it together.** Toolchain, dependencies, compile. Say what you are doing and why, at the
   user's level — this is their introduction to the model, not just a prerequisite you clear.
2. **Run the model's OWN sample / reference case**, unmodified. Not an A2MC ensemble, not a case you
   invented: the thing its developers ship and its docs describe.
3. **Confirm it produced output, and open it together.** Variable names, dimensions, units, time axis.
   This is where both of you learn what the model actually emits — and it is the evidence Step 5–6's
   parsers get written against.
4. **Check the adapter can read it** once parsers exist (or note the shape now, for when they do).
5. **Record what was built and run** — source URL, commit, toolchain and modules, the exact commands,
   the test that proves the binary exists, machine, sample case and output path — in
   **`models/<name>/BUILD.md`**, the model's one build guide, which ships with the adapter. `a2mc-init`
   Step 2 sends every later user of this model there, so the next person inherits a **fact** rather than
   an assumption about whether this model runs here. Archive the binary (`tools/model_archive_build.sh`).

### If the build fails

Keep going; do not hand it back. Resolve the toolchain, read the model's build docs, try the known
variants (compiler, MPI, PETSc pin, module set). Escalate to the model's own team **only with a
specific, tested question** — "we tried X, Y, Z; failure is F at line L" — never as *"we need you to
supply a binary."* If it is genuinely blocked, record the **tested** blocker with what was attempted in
`models/<name>/BUILD.md`, so the next session re-derives rather than re-reports (`20260807f`). A blocked
build does not block steps 1–10, which run on the model's shipped sample files (§"Sequencing rule").

**Outputs of this step:** a working build, a real sample output file, a run recipe that works on this
machine, and two people who have seen the model run. Those are exactly Step 0's "preconditions" —
produced, not demanded.

## The arc at a glance

| step | What happens | Skill / tool | Gate |
|---|---|---|---|
| 0a | **Where things go** — source checkout, archive root, orientation-run directory, and on a cluster the account | ask the user | answers held as `CHECKOUT` / `ARCHIVE_ROOT` / `RUN_DIR` |
| 0b | **Wire the checkout's fork-only push guard** | `git remote set-url --push origin DISABLED_…` | both push directions verified |
| 0c | **Characterize the codebase** — language, layout, param/output mechanics, run model | read the source tree | the 7-question profile is filled in |
| 0d | **Orientation run** — build it and run its own sample case, with the user | the model's own build + sample case | a real output file exists and was READ; the run recipe works here |
| 1–2 | Read the questionnaire (the agent), scaffold `models/<name>/` from `_template/` | `scripts/init_adapter.py --model <name>` | scaffold created |
| 3 | Codebase wiki (commit-pinned) | **`generate-codebase-wiki`** | wiki dir exists |
| 4 | Wiki ↔ source validation | **V1** `tools/validate_wiki_vs_source.py --model <name>` | Green/Yellow |
| 5–6 | Extract param/output surface; write real parsers | `models/<name>/{parameter,output}_parser.py` | parses real files |
| — | **Adapter conformance** | **V4** `adapter_conformance_validator.py` | ≥ Yellow |
| 7 | Curated seed (Recipe G1, PI-in-the-loop) | `scripts/curated_seed_builder.py` / **`inject-knowledge`** | seed written AND `tools/validate_seed_coverage.py` passes |
| 8 | Curated-YAML ↔ wiki validation | **V2** `yaml_wiki_validator.py` | Green/Yellow |
| 9 | RAG build + milestone registration | `scripts/build_<name>_rag.py` via **`build-rag-from-scratch`** + `rag/milestones.json` | index built and committed; milestone registered; **`model_preflight` against `$CHECKOUT` reports match** |
| — | RAG diff vs reference (+ FATES regression) | **V3** `rag_diff.py` | no regression |
| 10 | Seed adaptive memory | `memory/<name>/gained_knowledge/` | **4 stores exist AND `MemoryManager` returns non-empty context** — `check_stage_ready.py --model <m>` |
| 11 | Pick + render run template | `models/_template/runtemplates/` | — |
| 12 | Run-template validation | **V5** `run_template_validator.py` | parses, `{{VAR}}` resolved |
| 13 | Smoke test | `tests/test_<name>_e2e.py`: the offline chain (parse → bounds → parameter sets → write_parameter_file → extraction) on the sample outputs | the test passes; no binary needed |
| 14 | Calibration wiring | the case template `use_cases/<Model>_template/` + the targets contract + the ranking seam | `tools/create_use_case.py`, `tools/validate_model_targets.py`, `screen_ensemble` backend branch | `create_use_case.py --model <name> --case Demo --dry-run` resolves the template; the first ranked table comes from `onboard-case`'s first round |

> **Step 10 is the one step whose omission is invisible at every layer**, which is why its gate is
> spelled out rather than left to the next row. There is no successor validator, and the consumer
> degrades silently: `MemoryManager` pointed at a directory that does not exist raises nothing and
> returns 0 chars of context with all-zero stats, so the reasoning loop runs with **no model
> knowledge at all** and never complains. Measured 2026-08-19: PFLOTRAN went three weeks without it
> (`20260819h`). Contrast step 11, whose blank gate is cosmetic — skip it and step 12's V5 fails
> loudly, both when `runtemplates/` is absent and when it exists but holds no `*.tmpl`.

The whole `validate-rag-chain` skill runs V1→V2→V3 in order — use it rather than invoking the
three validators by hand once the seed exists.

## Recipe — end to end

```bash
# 0. Scaffold (dry-run first). The questionnaire guides YOU; the script takes no questionnaire flag.
python scripts/init_adapter.py --model <name> \
  --param-file <param.nc|json> --output-cdl <output.cdl> --dry-run
python scripts/init_adapter.py --model <name> \
  --param-file <param.nc> --output-cdl <output.cdl>
```

1. **Wiki (step 3).** `generate-codebase-wiki` → `docs/<name>-knowledge-base/<name>-codebase-wiki-<commit>/`.
   Commit-pin the dir name. Then **V1** — use the model-generic `tools/validate_wiki_vs_source.py
   --model <name> --wiki <dir> --source <src>` (it dispatches through the spec's `source_extensions`/
   `routine_decl_patterns`/`module_file_pattern`); the FATES `codebase_wiki_validator.py` is the untouched reference.
2. **Output surface (step 5).** If the model ships a real history tape, read *that* (it is the
   authoritative registry) rather than source-scanning — see `scripts/extract_ecosim_outputs.py`
   as the pattern. Emit CDL in the **indented `:attr = "..."`** style the `output_parser`
   recognizes (the qualified `varname:attr` style from raw `ncdump -h` is silently dropped).
3. **Parsers (step 6) — the adapter package.** Fill `models/<name>/`: `spec.py` (from source-cited
   wiki findings + domain vocabulary), `version.py` (commit-based detector + bump-tier classifier),
   real `parameter_parser.py` + `output_parser.py`, `backend.py`, `datasets.py`, `prompts.py`,
   `README.md`. **Contract interface (mandatory):** no-arg `__init__` + `parse(file_path)` — see
   Footgun 1. Run **V4** `adapter_conformance_validator.py` and drive Red→Yellow (Yellow is
   correct for a RAG-stage adapter: `curated_seed.yaml` + `runtemplates/` legitimately deferred).
4. **Curated seed (step 7).** `curated_seed_builder.py --model <name> --wiki <dir> --param-file …
   --output-cdl … [--user-guide pdf]` (default `--mode prompt-pack` = PI-in-the-loop). This is the
   most leveraged, most human-intensive step — its quality decides whether Phase 3 diagnosis can
   recommend parameters. Hand-authored additions go through `inject-knowledge`.

   **GATE IT — the builder cannot tell you it produced a partial seed.** It prints
   `[SKIP] category X has no assigned mechanisms` and then **exits 0**, so a half-covered seed reads
   as a finished one, and a parameter no mechanism names is invisible to Phase 3 no matter how well
   the wiki documents it. Run:

   ```bash
   python tools/validate_seed_coverage.py --seed models/<name>/curated_seed.yaml
   ```

   C1 = every category with parameters has ≥1 mechanism; C2 = every calibratable parameter is named
   by ≥1. It also accepts the builder's work-in-progress pair (`stage_b_categories.yaml` +
   `stage_c_mechanisms.yaml`), so it can gate the step *before* the seed is assembled. Model-agnostic
   — verified on the EcoSIM seed (PASS 10/10, 44/44), the PFLOTRAN seed (FAIL, 4 unreachable) and a
   FATES `curated_relationships_*.yaml` (FAIL). **Do not treat FAIL as cosmetic**: an unreachable
   parameter is one the calibration can never be told to move.

   **Also curate the SCORED TARGETS, not only the parameters.** Graph `affects` edges are built from
   `mechanisms[*].affects`, so an output no mechanism names has **zero incoming edges** and the graph
   cannot answer "what reaches my binding target" for it. Measured 2026-09-06 on an onboarded model:
   all four variables one case scored had zero incoming edges — 20 of 581 outputs were wired and every
   wired one belonged to a *different* case, because each case's targets had been added as they were
   onboarded and this one's never were. Check with a one-liner over `rag/graphs/<profile>.json` after
   the build: every scored target in the case's `validation/targets.yaml` should have in-degree ≥ 1.
5. **RAG build + milestone (step 9) — ONE BUILD SCRIPT PER MODEL.** Write
   `scripts/build_<name>_rag.py`, a sibling of the existing per-model family:

   ```
   scripts/build_rag_index.py       FATES/ELM  (ELMFATESVersion-shaped)
   scripts/build_ecosim_rag.py      EcoSIM
   scripts/build_pflotran_rag.py    PFLOTRAN
   (build_ats_rag.py exists on the ATS feature branch only; ATS has not reached step 9 here)
   ```

   Start from the closest existing sibling and adapt it. It must call the parsers **via the
   `models/<name>` package**, not a `rag/<name>_*` copy (Footgun 2). Register `<name>-<commit>` in
   `rag/milestones.json` (non-FATES models use the generic `adapter`/`model_commit_built`/
   `model_wiki_subdir` schema `ecosim-2dea74d9` established). Build:
   `$PY scripts/build_<name>_rag.py --rebuild`. Then delegate the surrounding chain to
   `build-rag-from-scratch` (Path N).

   **Then run the pre-flight check against the checkout the milestone was built from.** It is the first
   point at which `model_preflight` can succeed for this model:

   ```bash
   python tools/model_preflight.py --model <name> --checkout "$CHECKOUT" --param-file <the sample parameter file from Step 0d>
   ```

   It must report **match** (exit 0). Anything else means the milestone just registered does not resolve the checkout it was built from, most likely a wrong `model_commit_built` or a `version.py` that reads the commit wrongly, and every later user of this model would meet it as DRIFT or CANNOT VERIFY instead.

   **Do NOT merge these into one cross-model builder.** See "Per-model scripts" below — this was
   tried on ATS and reversed.
6. **Validate the chain.** `validate-rag-chain` (V1→V2→V3). V3 `rag_diff.py` doubles as the
   **regression gate**: the FATES `api-43-1` profile must stay byte-identical — a new model must
   not perturb the shipped index.
7. **Execution (steps 11–13).** Pick a `runtemplates/` variant (HPC×local × CIME/python/standalone),
   run **V5** `run_template_validator.py`, then write and pass `tests/test_<name>_e2e.py`: the offline
   chain on the model's sample outputs (siblings: `tests/test_ecosim_e2e.py`, `tests/test_pflotran_e2e.py`).
   **No binary and no HPC run is needed.** There is no orchestrator dry-run mode, and the orchestrator
   cannot be constructed for a non-CIME model today, so do not write the smoke test against it.
8. **Calibration wiring (step 14) — make it actually calibratable.** A2MC's "param-list → ranked
   evaluation" driver already exists and is model-generic at the ranking core
   (`phases/phase2_screening/screen_ensemble.py` + `tools/optimize_function.py` +
   `tools/targets_loader.py`); you WIRE the model to it, you do NOT write a new driver.

   > **The first case is created by `onboard-case`, not here.** Invoke it once the adapter exists —
   > it runs the science-goal interview, the research-plan gate, the scaffold, the parameter list and
   > the readiness gate, and it is the same skill the user runs for their second and tenth case.
   > **What follows is the MODEL-side half** — the facts `onboard-case` needs from you and the wiring
   > only a model author can do (which machine config, which template to author, the parameter-list
   > schema, the targets contract, the ranking seam). Do the wiring here; let `onboard-case` drive the
   > case. Duplicating its steps here is what left a second case with no entry point until 2026-08-02.

   The model-side wiring:
   - **Machine config — pick by whether the model is CIME-driven.** It was written in `a2mc-init`
     Step 3 before this skill started; here you record which file the model's site configs load. CIME-based
     model (CTSM/CESM/E3SM family, sharing E3SM infra per Step 0) → `a2mc_config.sh`; standalone-binary /
     non-CIME model (EcoSIM, ATS, TEM, …) → `a2mc_noncime_config.sh`. For a **non-CIME model, source
     `a2mc_noncime_config.sh`, NOT `a2mc_config.sh`.**
     `a2mc_config.sh` is ~80% CIME/E3SM/FATES-specific (E3SM_ROOT, COMPSET, ADSP/RGSP/TRANS, and it
     DEFAULTS `A2MC_MODEL_PATH` to the E3SM checkout — which would shadow your model's checkout). The
     parallel `a2mc_noncime_config.sh` carries only the generic settings (AI config, python env,
     iteration, sampling, RAG dir) and sets NO `A2MC_MODEL_PATH`. The order is still machine→site,
     but since v2.306 the site config **auto-sources** whichever machine config its model needs, so
     `source use_cases/<name>_<site>/config/<...>.sh` alone is enough — give the template you author the same guard (copy it from an existing one; `tests/test_site_config_autosource.py` asserts
     every shipped config has it). (The two
     machine files mirror their AI/iteration/sampling blocks — keep-in-sync comment in both; kept
     separate rather than DRY-factored so `a2mc_config.sh` stays byte-identical to `main`, docs/38.)

     > An **agent** running these commands joins the `source` to the command that needs it (`source … && <command>`): each shell call is a fresh process. Full statement: `AGENTS.md` §"Source the config and run in the SAME command".

   - **Site config — AUTHOR THIS MODEL'S TEMPLATE DIRECTORY; `onboard-case` does the copy.** Your
     job is **`use_cases/<Model>_template/`** (architecture B, PI 2026-08-17): a site-agnostic
     authored case with every site value a `<PLACEHOLDER>`. At minimum
     `config/<model>_template_config.sh` and `config/calibration_rounds.yaml`, plus
     `validation/targets.yaml`, `README.md`, and **any run-control file this model's run style
     needs** — EcoSIM ships `case_template/run.nml` and an `OPTIONS.md` reference beside it.
     `create_use_case.py` defaults to this dir and copies it verbatim.
     **It is AUTHORED, not generated** — earlier it was a regenerated snapshot of
     `use_cases/TEMPLATE/`, which is precisely why a per-model file could not live in one and why
     every scaffolded EcoSIM case pointed at a namelist that did not exist (`20260816a` F1). Adding
     a per-model file is now just adding a file: no `EXTRA_TEMPLATE_FILES` row, no suffix
     convention, and nothing regenerates over it. **Templates are PER MODEL and site-agnostic** (2026-08-02): `fates_` (CIME),
     `ecosim_` (standalone namelist), `pflotran_` (deck + thermodynamic database) — run styles
     differ, so there is no single generic one. Put the model's own `README.md`,
     `validation/targets.yaml` and `config/calibration_rounds.yaml` **inside** the template directory:
     without them a new case falls back to the generic seed, whose targets header asserts FATES's
     `PFT<id>_<vartype>` bare-key convention — actively wrong for an adapter model
     (`tools/targets_loader.py`: that resolution is FATES-only; adapter models set `variable`/`pft`/
     `window`/`reduce` explicitly).
     The template pre-wires the standard file vars — `A2MC_PARAM_LIST_FILE`, **`A2MC_ENSEMBLE_MATRIX_FILE`**,
     `A2MC_SALIB_PROBLEM_FILE`, `A2MC_VALIDATION_TARGETS`, `A2MC_CASE_NAME_PATTERN` — so a fresh site is
     wired end-to-end; hand-writing the config is how a var silently gets dropped (EcoSIM's config was
     hand-written and missed `A2MC_ENSEMBLE_MATRIX_FILE` until `20260715e`). It then sets `A2MC_MODEL=<name>`,
     `A2MC_MODEL_PATH`, and (for a **non-CIME adapter**) swaps the template's FATES/CIME-specific bits
     (base-param JSON path, §5 mode-aware/ELM_OPTIONS/PARTEH) for the backend's run inputs
     (binary/base-namelist/runtemplate keys) + HPC account/queue + `A2MC_OUTPUT_DIR`. (EcoSIM exemplar:
     `use_cases/EcoSIM_template/config/ecosim_template_config.sh`, which ships everywhere.) A standalone
     base namelist MUST use ABSOLUTE input paths (`create_case` repoints only the parameter file, not
     the other forcing inputs — a relative `../../input/…` breaks from an ensemble case dir); give the
     site its own `case_template/` namelist. Exploratory run-length (e.g. EcoSIM `stop_n`) is a KEY
     knob — set it to one forcing cycle over the target window, not a full equilibrium spinup × N cases.
   - **Parameter list — the CANONICAL explicit-column format.** One row = one independently-sampled
     value = one Morris matrix column. **The canonical form is EcoSIM's** (PI, 2026-08-02): `name` +
     `pft` + bound columns carrying the `_bound` suffix, plus the recommended `default`,
     `description` and `bound_source`. Two of the three models already used it, and it is the only
     one with `bound_source`, which the bounds-provenance pipeline needs. **Author a new model's list
     in this form; convert a user-supplied list on intake** (`onboard-case`).
     **★ RULE: `name` holds ONLY the official parameter name as it appears in the model's param file;
     the group id is its OWN column — NEVER baked into the name (`VCMX` + `pft=1`, NOT `VCMX_1`).**
     A2MC builds the canonical id from (name, pft) and the backend interprets it → the param-file
     slot; a name with the id baked in breaks that interpretation and the per-group dispatch.
     **Name the bound columns with the `_bound` suffix, not the bare words** — `_find_header_row`
     matches the bare form on a WHITESPACE split, so in a comma-separated header it never matches
     and the file does not parse at all. Template + full schema (integer group, named group,
     global/scalar): `use_cases/TEMPLATE/parameters/parameter_list_template.csv`, read by
     `scripts/create_adapter_parameter_sample.py::parse_pft_param_list` (id `{name}_{pft}`).
     **The axis set is EXTENSIBLE, and that is the point.** `pft` and `organ` are the BASIC axes
     and both ship in the template; a model **adds** the axes it needs as further columns
     (`mineral`/`phase` for PFLOTRAN, a microbial guild, a chemical species), and a coupled run
     carries several at once. A row is identified by `name` plus every non-blank axis cell, so
     adding an axis renames nothing that already exists. **Add a column — do not overload `pft`
     with a non-PFT meaning, and do not rename `pft` to something neutral**; `pft` is meaningful
     where it appears, and a neutral name loses that.
     *Interim:* the id builders consume ONE axis today (`ModelSpec.grouping_axis`,
     `models/base.py:199`, is a singular `str`; the adapter loader ids on (name, pft); only
     `tools/param_spec.py` reads `organ`). So a model whose axis is not PFT currently puts its
     value in `pft` as a stopgap — which is what PFLOTRAN's live list does with mineral names, and
     is a **symptom of the singular axis, not the target schema**. Declare the real axis column
     anyway. The FATES legacy dialect (`fates_name`, bare bound names) is retained only because the
     live Kougarok 168-parameter list must not be rewritten under a running round; do not start a
     new list there.
     **`bound_source` uses a controlled vocabulary** — `measured:` (this project's own data),
     `literature:` (citation AND a resolvable DOI), `database:` (TRY / FRED / FLUXNET, naming the
     record + DOI), `prior_round:`, or `provisional:` with the basis stated. Never blank.
   - **Baseline = the base param file at documented defaults; run it as V0 first.** Verify the base
     parameter file's per-PFT values MATCH the param list's `default` column, so the *unperturbed*
     base IS the documented baseline (EcoSIM R1: 40/40 exact, `20260715e`). If they drift, either fix
     the `default` column or rebuild the base from defaults
     (`backend.write_parameter_file(base, {defaults}, out)`). Then run the base UNPERTURBED as an
     explicit **V0 baseline case** — the reference the ensemble cases are scored against and a
     reproducibility anchor. The base must be one the binary actually RUNS (footgun 7); a base that
     "runs but decays/underperforms" is still the correct calibration baseline when *eliminating that
     gap* IS the objective (don't wait for an externally-tuned base — the gap is what you calibrate).
   - **Sample → materialize per-case parameter files → submit** (the Phase-0 ensemble; adapter path —
     the analog of FATES's `create_parameter_sample.py` → `generate_parameter_files.py` → submit).
     (1) **SAMPLE:** `scripts/create_adapter_parameter_sample.py --method morris …` reads the explicit
     param list → the N×P matrix + SALib problem. It **imports** the shared SALib sampler; it does NOT
     edit `phases/phase0_design/create_parameter_sample.py` (byte-locked to main, docs/38). (2)
     **MATERIALIZE (the create-param-files-from-the-matrix step):** `scripts/materialize_adapter_ensemble.py
     [--baseline] [--dry-run]` maps each matrix row → `{canonical_id: value}` via the SAME parser
     (column j ↔ names[j], no reordering) → `backend.write_parameter_file` (per-PFT/organ write) →
     `backend.create_case` (one self-contained case dir: param file + runfile.nml + submit.sh). `--baseline`
     also writes the unperturbed **V0** case; it writes FILES ONLY. (3) **SUBMIT:** separately and
     deliberately (`backend.submit_ensemble`). `run_smoke_ensemble` (2 corners) is the smoke-test analog;
     this is the full-matrix path.
   - **`validation/targets.yaml`** in the `targets_loader` schema, each target naming an explicit
     `variable` (that EXISTS on the model's output registry — inactive-by-default vars must be
     activated, see `ecosim-version-drift` §B), a grouping-axis `pft`, a peak-season `window`+`reduce`,
     and a scalar `observed`. **Validate it: `tools/validate_model_targets.py --model <name> --targets …`**
     (catches nonexistent/inactive vars, missing observed, bad windows before an ensemble runs).
   - **The ranking seam is already backend-dispatched** (additive, docs/38): when `A2MC_MODEL` is a
     registered backend, `screen_ensemble.load_ensemble_simulated` extracts each case via
     `backend.extract_history_variables` + `model_evaluate_case.reduce_target` (masking model spval
     → NaN) instead of the FATES SZPF path — so a **new model inherits the whole ranking machine for
     free**. Verify: `run_smoke_ensemble` (small N) → `model_ensemble_status --watch` → `screen_ensemble`
     yields a ranked table. If your model's target extraction has a non-flat grouping (like FATES SZPF),
     override `ModelBackend.select_group_series`.

## Hand off to `onboard-case`

Onboarding ends when the model is **calibratable**, not when a case exists. Confirm it with
`python3 tools/check_stage_ready.py --model <name>` (no ✗), then close by invoking **`onboard-case`** for
the user's first project on this model — it takes the template you authored in step 14, binds the case
to the binary Step 0d built and archived (its Step 2), and carries the user to Phase 0. Every later case
runs the same skill; `onboard-model` does not run again.

Pass it the Step 0a answers: `onboard-case` round 1A starts from the checkout and the archived binary, and asks only for what belongs to the case, its output root and the account it charges.

## Sequencing rule (proven by real onboarding)

Do the **knowledge chain + reasoning phases first** (they run on existing sample outputs), the
**execution phases last** (they need a compiled model + ensemble). Step 0d always **attempts** the build;
if it is genuinely blocked, the tested blocker goes in `BUILD.md` and steps 1–10 continue on the model's
shipped sample files. Don't block the whole onboarding on an HPC-ready binary.

Corollary, proven on ATS: step 13's smoke test needs **no compiled binary**. Only Phases 0/5 submit
jobs. Do not mark it blocked on a binary — the offline chain (parse → bounds → parameter sets →
write_parameter_file → extraction from an existing/synthesized output) runs today. See
`tests/test_ecosim_e2e.py` (and `test_ats_e2e.py` on the ATS branch, which is where that
corollary was proven).

## Per-model scripts (PI rule, 2026-08-01)

**A2MC keeps one script per model, in parallel — the agent uses a model's own scripts when they
exist.** This governs the RAG builder and any future per-model tooling.

1. **Do not merge scripts across models.** Two models is not a mandate to merge. Separation keeps
   the blast radius of a change at one model, and lets each script read its own model's shapes
   directly instead of behind a dual-shape seam.
2. **Genericity is earned by covering EVERY model in A2MC**, not by covering two.
3. **The axis of genericity is the CASE STUDY within a model, not the model.** A per-model script
   must work for any site/deck/milestone of that model — take the input as an argument
   (`--profile`, `--param-file`), never hardcode one case study.

**This was tried the other way and reversed.** On ATS I generalized `build_ecosim_rag.py` into a
cross-model `build_adapter_rag.py --model <name>`, reading the EcoSIM script's docstring ("the
D-pass unifies this…") as sanction. An anticipated refactor in a docstring is a **plan, not an
approval**. The merge also created work that only existed because of it — a cross-model regression
run against EcoSIM, whose RAG had already been built during its own onboarding. Reverted in
`20260801h`; renamed to build_ats_rag.py (on the ATS branch).

Two concrete costs of the merged form, both measured:

- it needed a dual-shape `_field()` accessor purely to bridge EcoSIM's **dataclass** records and
  ATS's **dict** records — a per-model script just reads its own;
- it **silently dropped information**: it read `dimension_level`, a field ATS records lack, so every
  ATS output node carried `level: null`. The ATS-specific script reads `functional` and recovers it.

> **When changing any build script, DIFF the graph, don't trust the counts.** The count-regression
> guard only fails on a >2% **shrink**, so a regression that ADDS nodes/edges passes silently. A
> one-word slip (`par.get("category") or "uncategorized"`) wired 24 solver/IO numerics into the ATS
> graph as physics and the guard was happy; an explicit node/edge diff caught it.

## Footguns (each cost real time on the EcoSIM onboarding)

1. **Parser contract, not the legacy FATES shape.** The A2MC adapter contract
   (`models/_template/parameter_parser.py`, V4 line ~454 `parser_class().parse(file_path)`) is a
   **no-arg constructor + `parse(file_path)`**. FATES's own `rag/parameter_parser.py` is
   grandfathered on the *legacy* path-in-constructor + no-arg `parse()` shape — do **not** copy it.
   V4 catches this; it was invisible until EcoSIM (the first adapter on the new contract).
2. **`models/<name>/` vs `rag/<name>_*`.** Recipe 2 (older, in `rag_build_roadmap.md`) put new-model
   parsers at `rag/<model>_*`; the newer contract (docs/17/19, `models/_template/`) puts them at
   `models/<model>/`. Follow the newer contract — the RAG-build wiring must import the
   `models/<name>` package.
3. **No common parameter prefix ≠ no parameters.** If the model's params aren't `fates_`-prefixed
   (EcoSIM uses uppercase Fortran names `ICTYP`/`VCMX`/…), `param_name_regex` can't be a prefix —
   treat **every non-string variable** in the param file as a candidate parameter, grouped by
   source file, PFT axis = any of `npfts/npft/pft/maxpfts`.
4. **Use the model-generic validators/tools (distilled from the EcoSIM onboarding).** V1/V2/V5 now have
   spec-dispatched `--model` versions — `tools/validate_wiki_vs_source.py`, `tools/validate_curated_yaml.py`,
   `tools/run_template_validator.py` — plus `tools/model_preflight.py` (version+PFT), `tools/model_evaluate_case.py`
   (obs↔sim), `tools/check_ecosim_rag_queries.py --profile`. Run these with `--model <name>`; the FATES/EcoSIM
   originals are the untouched reference. (The V3 profile-diff `rag_diff.py` is still FATES-shaped.)
5. **Python 3.10 + CDL attribute style** (see the two callouts above).
6. **The parameter description LIES — verify definitions/units in SOURCE.** A param's netCDF
   `long_name` AND its `units` attribute can be wrong; the truth is how the internal variable is
   *used in the equations* (Calibration Rule #2). On the EcoSIM onboarding this bit repeatedly: `CNLF`/
   `CPLF` are *maxima* not operative values (measured lit describes the model OUTPUT — don't clamp);
   `UPKMPO`'s unit attribute said µM but the model uses g P m⁻³; `SLA1` is a power-law coefficient
   not bulk SLA; `XDL = −1` is a disabled sentinel. **Gate the curated seed (step 7) + any bounds on
   source-verification** — trace read → internal var → usage before trusting a description.
   `[[feedback_param_description_can_lie_verify_in_source]]`.
7. **Input↔binary version compat — fail fast before submitting.** The built binary and the sample
   input file can be from different commits (EcoSIM: the binary read 17 pft vars the input lacked →
   a wasted submit + mid-read abort). Declare `spec.input_reader_sources` + `input_read_pattern`, and
   run **`python tools/model_check_input_compat.py --model <name> --checkout <src> --param-file <in>`**
   as a pre-submit gate (`20260712f`).
8. **Slurm success ≠ model success.** A standalone-binary run can exit Slurm-`COMPLETED` yet produce
   no output tape (a model failure). Monitor with **`python tools/model_ensemble_status.py --model
   <name> --run-root <dir>`**, which reconciles the two (no-tape = FAILED). For the ensemble itself:
   `scripts/run_smoke_ensemble.py`; for provisional bounds: `scripts/model_generate_bounds.py`.

## Where each onboarded model stands

| model | status on this line | milestone |
|---|---|---|
| EcoSIM | the first model driven through this skill; fully onboarded, with cases calibrated end to end | `ecosim-2dea74d9` |
| PFLOTRAN | the second; fully onboarded. Rebuilt on Perlmutter 2026-09-23 on `cpe/25.09` after its first toolchain was removed (`models/pflotran/BUILD.md`) | `pflotran-157a26f7` |
| ATS | adapter and parsers done; stopped before step 9 (no milestone, memory store or run template) | none: resume at `check_stage_ready.py --model ats` |

`python3 tools/check_stage_ready.py --model <name>` is the live answer; this table is a snapshot.

## Cross-references

- Historical overview (superseded 2026-08-26; its dashboard is a 2026-07-06 snapshot): `docs/A2MC_Adapter_Kit_Master_Plan.md`
- Contract / implementation: `docs/17_*`, `docs/19_*`
- Step how-tos: `docs/a2mc_reference/{codebase_wiki_generation,rag_build,graphrag_curated_yaml,rag_validation,version_association}*.md`
- Delegated skills: `generate-codebase-wiki`, `build-rag-from-scratch`, `inject-knowledge`, `validate-rag-chain`, `rebuild-rag`
- User-facing narrative twin (planned, not yet written — Master Plan §8 #3): a `forking_a2mc_for_a_new_model` roadmap under `docs/a2mc_reference/`

