# A2MC User Guide

Detailed companion to the top-level [`README.md`](../../README.md). The README is the front door (what A2MC is, how the two agents work, the 7-phase overview, a condensed quick start). This guide holds the full operational detail: configuration reference, per-phase behavior, module APIs, the knowledge system internals, and the operational concerns (state persistence, error handling, cost, reporting).

## Which models A2MC works with

A2MC is **not ELM-only**. The framework is model-agnostic; each model is reached through an adapter
in `models/<name>/` plus its own knowledge chain (source-grounded wiki → curated seed → RAG profile).

| model | status | what exists today |
|---|---|---|
| **ELM / ELM-FATES** | **supported** — the worked reference | milestones `api-43-1`, `api-31-0`; the Kougarok reference case |
| **EcoSIM** | **supported** | adapter, milestone `ecosim-2dea74d9`, RAG + curated seed, two live cases (BioCON, Lusignan) |
| **PFLOTRAN** | **supported**; case work in progress | adapter, milestone `pflotran-157a26f7`, RAG + curated seed, the miniLEO case (its `extract`/`evaluate` path is still being finished) |
| **ATS** | **in progress** | adapter and knowledge base built on a feature branch; no registered milestone or run template in this release yet |
| **ecosys** | **planned** | not scoped in-repo yet. (EcoSIM descends from ecosys, so much of the groundwork is shared.) |
| **TEM** | **planned** | not scoped in-repo yet |

**Check what *this* clone actually supports** rather than trusting a table that can age:

```bash
python3 scripts/rag_list.py                 # registered milestone profiles
ls models/                                  # adapters present
python3 tools/check_stage_ready.py          # which setup stage you are in
```

Adding a model A2MC has never seen is the **`onboard-model`** skill, which is the adapter kit's whole
premise: *import A2MC to calibrate models other than ELM.*

## Contents

0. [Which models A2MC works with](#which-models-a2mc-works-with)
1. [Installation and setup (NERSC Perlmutter)](#1-installation-and-setup-nersc-perlmutter)
2. [Configuration reference](#2-configuration-reference)
3. [Using the offline (interactive) agent](#3-using-the-offline-interactive-agent)
4. [Using the online (autonomous) agent](#4-using-the-online-autonomous-agent)
5. [The 7-phase workflow in detail](#5-the-7-phase-workflow-in-detail)
6. [Module reference](#6-module-reference)
7. [Knowledge system](#7-knowledge-system)
8. [Adaptive memory system](#8-adaptive-memory-system)
9. [Experimental design strategies](#9-experimental-design-strategies)
10. [State persistence](#10-state-persistence)
11. [Integration with existing tools](#11-integration-with-existing-tools)
12. [Error handling](#12-error-handling)
13. [Cost management](#13-cost-management)
14. [Calibration logs, cycle reports, and round reports](#14-calibration-logs-cycle-reports-and-round-reports)
15. [Directory structure](#15-directory-structure)

---

## 1. Installation and setup (NERSC Perlmutter)

### The guided path — start here

**You do not have to configure A2MC by hand.** The offline agent (a coding-agent harness opened in
this repo) drives setup through skills, and each stage has a checklist and a runnable gate:

| your situation | start with |
|---|---|
| fresh clone, model A2MC already supports | **`a2mc-init`** — verifies your checkout against the RAG milestone registry, offers fork-safe remotes, writes the machine config, then routes onward |
| a model A2MC has never seen | **`onboard-model`** first — including **Step 0d, the orientation run**: A2MC builds the model with you and runs its own sample case, so neither of you is reasoning about a model nobody here has executed |
| adding a case to an onboarded model | **`onboard-case`** — interview → research plan → `use_cases/<Model>_<Case>/` → parameter list → Phase 0 |
| resuming an already-configured clone | **`onboard-session`** — reads the active case's `memory/workflow_state_offline_r{RR}.json` (highest round) for where the loop stands, its `next_action`, and any Phase-6 binding target, and validates it before acting on it; re-reads the project's operating rules, checks the branch and uncommitted work, reads the latest calibration log or round report, looks for in-flight HPC jobs and arms monitoring, and surfaces any pending knowledge proposals. It then **drives that next action** rather than reporting and waiting |

Not sure which? **Ask the repo, not yourself:**

```bash
python3 tools/check_stage_ready.py          # which stage am I in, and what is outstanding?
```

It needs no sourced config (that is the point — it answers the question that comes *before* `check_setup_ready.py`), routes from what is on disk, and prints the items it cannot verify so a clean run is never mistaken for a finished stage. The full per-stage definition of done is the **`setup-discipline`** skill. A session that opens in an unconfigured clone is also told this automatically by the `SessionStart` hook.

The manual steps below are what those skills automate — read them to understand the machinery, or to work without an agent harness.

### Manual installation

```bash
# 1. Clone the release you are using
# A2MC is the non-CIME release: the framework plus the models/ adapter registry
# (EcoSIM, PFLOTRAN, ATS) and onboard-model. If your model is a CIME-configured
# Earth system model (ELM, ELM-FATES), clone A2MC-elm instead -- it carries the
# built-in FATES path and the Kougarok reference case. If you were given a fork
# for your model, clone that. The rest of this guide is the same either way.
cd /global/homes/$USER
git clone https://github.com/jingtao-lbl/A2MC.git
cd A2MC

# 2. Set up Python environment (ONE-TIME setup)
# CAUTION: `module load python` is for creating the venv ONLY. Do NOT leave it in a shell where you
# run CIME: it shadows ~/a2mc_env's Python 3.11 (the interpreter the ensemble was built with) and
# `create_newcase` dies. After setup, `source a2mc_config.sh` activates the right one; assert with
# `python3 --version` before any run. A --dry-run does NOT catch this.
module load python
python -m venv ~/a2mc_env
source ~/a2mc_env/bin/activate
# anthropic SDK for the Anthropic provider; openai SDK for OpenAI/CBorg providers
pip install anthropic openai numpy pandas xarray netCDF4 scipy SALib networkx chromadb sentence-transformers pyyaml Pillow

# 3. Set API key (add to ~/.bashrc for persistence)
# Use the env var matching your provider (see a2mc_config.sh -> A2MC_AI_PROVIDER):
#   anthropic -> ANTHROPIC_API_KEY, openai -> OPENAI_API_KEY, cborg -> CBORG_API_KEY
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
source ~/.bashrc

# 4. Verify setup
python -c "import anthropic; print('Anthropic SDK OK')"
python -c "from orchestrator import CalibrationOrchestrator; print('Orchestrator OK')"
```

After initial setup, the virtual environment is auto-activated when you `source a2mc_config.sh`. Keep your API key visible only to yourself (e.g., `chmod 600 ~/.bashrc`).

---

## 2. Configuration reference

A2MC uses a two-level configuration hierarchy:

- `a2mc_config.sh`or `a2mc_noncime_config.sh` — machine-level defaults (HPC paths, COMPSET, Python env, simulation protocol, AI provider).
- `use_cases/{site}/config/{site}_config.sh` — site-specific overrides (PFTs, parameters, validation targets, protocol overrides).

**You customize both files. You source only the second one.**

Editing is a two-file job: machine settings belong in `a2mc_config.sh` or `a2mc_noncime_config.sh`(§2.4) and everything site- and round-specific in the site config (§2.2). Running is a one-command job — since v2.306 **the site config auto-sources the machine config**, so this is the whole chain before every run:

```bash
source use_cases/{model}_{site}/config/{site}_config.sh          # or the round wrapper, {site}_config_r<N>.sh
```

It loads `a2mc_config.sh` for a CIME model (ELM, ELM-FATES) or `a2mc_noncime_config.sh` for a standalone one (EcoSIM, PFLOTRAN, ATS), whichever that site's model needs, and only when one is not already loaded. If you sourced the wrong one by hand it **repairs** the choice rather than accepting it. The load happens at the top of the site config, so the effective order is unchanged — machine defaults first, site overrides on top, and a round wrapper's overrides on top of both.

Sourcing the machine config yourself first still works and is a no-op:

```bash
source a2mc_config.sh && source use_cases/{model}_{site}/config/{site}_config.sh
```

Check rather than assume — the three loop limits come from the machine config and from nowhere else, so they are the signal that the chain resolved:

```bash
echo "$A2MC_MAX_EXPERIMENTS $A2MC_MAX_SKIP_TESTING $A2MC_CONFIDENCE_THRESHOLD"   # none should be empty
```

### 2.1 Create a use case

```bash
# Copy the Kougarok example (recommended) or the minimal template
cp -r use_cases/ELM-FATES_Kougarok use_cases/YourSite
# OR
cp -r use_cases/TEMPLATE use_cases/YourSite
```

### 2.2 Site-specific settings

Edit `use_cases/YourSite/config/yoursite_config.sh`:

```bash
# SITE INFORMATION
export A2MC_SITE_NAME="YourSite"
export A2MC_SITE_LAT=45.0
export A2MC_SITE_LON=-120.0

# PFT CONFIGURATION
export A2MC_PFTS="1,2,3"                  # Your target PFTs
export A2MC_PFT_NAMES="PFT1,PFT2,PFT3"

# DOMAIN AND SURFACE DATA
export A2MC_DOMAIN_FILE="domain_yoursite.nc"
export A2MC_SURFACE_FILE="surfdata_yoursite.nc"

# PARAMETER CONFIGURATION
export A2MC_N_PARAMS=100                  # Number of parameters
export A2MC_N_TRAJECTORIES=30             # For Morris method
export A2MC_PARAM_LIST_FILE="${A2MC_USE_CASE_DIR}/parameters/your_param_list.txt"

# VALIDATION
export A2MC_VALIDATION_FILE="${A2MC_USE_CASE_DIR}/validation/your_targets.txt"

# HPC PATHS (ensemble output, parameter files)
export A2MC_PARAM_DIR="/path/to/fates_param_files"
export A2MC_ENSEMBLE_OUTPUT="${A2MC_OUTPUT_ROOT}/YourEnsemble"
```

### 2.3 Parameters and validation targets

Create these files in your use case folder:

```bash
# Parameter list with bounds
vim use_cases/YourSite/parameters/your_param_list.txt

# SALib problem definition (optional, for sensitivity analysis)
vim use_cases/YourSite/parameters/salib_problem.txt

# Validation targets
vim use_cases/YourSite/validation/your_targets.txt
```

### 2.4 Machine settings

Only edit `a2mc_config.sh` (or `a2mc_noncime_config.sh` for non-CIME models) if you need to change HPC-level settings:

```bash
export A2MC_PROJECT="your_project"        # HPC allocation
export A2MC_E3SM_ROOT="/path/to/E3SM"     # E3SM source code
export A2MC_OUTPUT_ROOT="/path/to/output" # Simulation output root

# REQUIRED for version-aware RAG (v2.90+): point at your E3SM/ELM-FATES checkout.
# A2MC reads the FATES + ELM commits and selects the matching RAG profile.
export A2MC_MODEL_PATH="/path/to/your/E3SM_FATES_checkout"

# Optional for configuration-aware retrieval (v2.92+): override mode env vars.
# Defaults match ELM namelist_defaults.xml (vanilla SP run, no FATES).
# Set in your site config to enable FATES with CNP + ECA, etc.
export A2MC_ELM_OPTIONS="-bgc fates -nutrient cnp -nutrient_comp_pathway eca"
export A2MC_FATES_PARTEH_MODE=2           # 1=carbon-only, 2=CNP
# Tier 2 FATES feature flags (default false):
#   A2MC_FATES_SPITFIRE_MODE, A2MC_USE_FATES_PLANTHYDRO,
#   A2MC_USE_FATES_LOGGING, A2MC_USE_FATES_SP, etc.
# See docs/a2mc_reference/mode_aware_workflow.md for the full 20-dim schema.

# Optional for auto-rebuild on drift (v2.98+):
# When the orchestrator detects your checkout has drifted off the matched
# milestone, this opts in to automatic rebuild for T2 / T3-near drift
# (subprocess + validator gate; rollback to <profile>.previous/ on failure).
# T3-distant drift always emits a prompt-pack and aborts regardless.
export A2MC_RAG_AUTO_REBUILD="false"      # default false (warn-and-continue)
export A2MC_RAG_T3_AUTO_DISTANCE=100      # default 100 = one major epoch step
# See docs/a2mc_reference/version_association_howto.md "Drift handling".
```

### 2.5 AI settings

For the online agent, AI reasoning is required for every phase except Phase 5, which calls built-in tools/scripts.

**Choose your provider** — edit `A2MC_AI_PROVIDER` in `a2mc_config.sh`:

```bash
export A2MC_AI_PROVIDER="anthropic"   # Direct Anthropic API (default)
# export A2MC_AI_PROVIDER="openai"    # Direct OpenAI API
# export A2MC_AI_PROVIDER="cborg"     # Berkeley Lab CBorg proxy
```

Each provider has a default model (set automatically when you source `a2mc_config.sh`); override with `A2MC_AI_MODEL`.

| Provider | Default Model | Other Models |
|----------|---------------|--------------|
| `anthropic` | `claude-opus-4-20250514` | `claude-sonnet-4-20250514`, `claude-haiku-3-20240307` |
| `openai` | `gpt-4o` | `gpt-4o-mini`, `o3-mini` |
| `cborg` | `anthropic/claude-sonnet` | `openai/gpt-4o`, `openai/gpt-4o-mini`, `lbl/llama` |

**Set the API key** matching your provider in `~/.bashrc` before sourcing `a2mc_config.sh`:

```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc   # for anthropic
# echo 'export OPENAI_API_KEY="sk-..."' >> ~/.bashrc        # for openai
# echo 'export CBORG_API_KEY="sk-..."' >> ~/.bashrc         # for cborg
source ~/.bashrc
```

---

## 3. Using the offline (interactive) agent

A2MC is **one agent that runs two ways** over the same substrate — the same operating rules, skills, memory, logs, and knowledge base:

| | **Autonomous (online)** | **Offline (interactive)** |
|---|---|---|
| What it is | `python orchestrator.py --run` — the fixed Phase 0→7 state machine calling the model in a loop | a coding-agent harness (Claude Code, or any equivalent) working in the repo by conversation |
| Best at | unattended execution at scale | open-ended, judgment-heavy, one-off work the loop cannot do |
| Curated knowledge | **proposes** — `MemoryManager` runs in `propose` mode, staging to `auto_discovered_pending.json` | **disposes** — the only writer of curated knowledge, after human review |

Section 4 covers the autonomous loop. This section covers the offline agent, which is also how most people **start**: it can interview you and build the use case that Section 2 otherwise asks you to assemble by hand.

Its operating contract is [`AGENTS.md`](../../AGENTS.md) — harness-neutral, so it does not assume any particular coding agent. Its capabilities are packaged as **skills** in `.claude/skills/`, each a `SKILL.md` the agent reads and follows; the full index is [`skills_catalog.md`](skills_catalog.md). Every skill declares a `modes:` block so the agent can check it against your run configuration.

**Setup is three stages here, not one**, because this release calibrates models A2MC has never seen (section 0) as well as ones it already knows. Ask the agent for **`setup-discipline`** to find out which stage you are in and what "done" means for it — a stage half-finished is worse than one not started, because the failure is silent.

| stage | skill | run it |
|---|---|---|
| 1 | **`a2mc-init`** | once per clone or machine |
| 2 | **`onboard-model`** | once per model A2MC has never seen — skip if yours is already in `models/` |
| 3 | **`onboard-case`** | once per case, repeatable |

```bash
python3 tools/check_stage_ready.py            # which stage am I in, and what is outstanding
```

### 3.1 Setting up a clone — `a2mc-init`

If you have just cloned A2MC and nothing is configured, this is the entry point. Ask your agent to run **`a2mc-init`** (in Claude Code, `/a2mc-init`). It greets you and gauges your experience with the model, confirms **which model you are calibrating and whether A2MC already supports it**, verifies your checkout against the RAG milestone registry, offers fork-safe remotes on that checkout, and writes the machine config — `a2mc_config.sh` for a CIME-configured model, `a2mc_noncime_config.sh` for a standalone one.

It then **routes onward** rather than doing everything itself: to `onboard-model` if your model has no adapter and no registered milestone yet, or to `onboard-case` to build the case. It will not invent a value you did not give — gaps are marked `TODO` — and confirms before writing any config.

### 3.2 Teaching A2MC a new model — `onboard-model`

This is the adapter kit's whole premise. **`onboard-model`** builds everything A2MC needs to reason about a model it has never seen: the `models/<name>/` adapter (how a case is built, run, extracted and scored), the source-grounded knowledge chain (codebase wiki → curated seed → RAG profile), and a registered entry in `rag/milestones.json` pinned to the model's source commit. Its acceptance gates are build-and-run validators, not a checklist — the model has to actually run through A2MC before the stage is done.

Skip this stage if `ls models/` already shows your model.

### 3.3 Adding a case — `onboard-case`

Once the machine is set up and the model is onboarded, each additional site or project is **`onboard-case`**: interview from the science goal, resolve the case scale, draft a research plan, scaffold `use_cases/<Model>_<Case>/` from that model's site-agnostic template, build or vet the parameter list, run the readiness preflight, hand off to Phase 0. The case folder is named `<Model>_<Case>` (`EcoSIM_BioCON`, `PFLOTRAN_miniLEO`) because every model has its own round 1.

The question script it works from is [`a2mc_init_interview_questionnaire.md`](a2mc_init_interview_questionnaire.md) — illustrative rather than authoritative, adapting depth to your stated experience and skipping questions a prior answer made irrelevant.

> One trap it guards, worth knowing regardless of how you set up: **`validation/targets.yaml` is calibration-only, and everything in it is scored.** Observations you only want to *compare* against belong in `validation/data/`, read by a purpose-built script. Nothing errors if you get this wrong — the round simply starts optimizing toward data you meant as a cross-check.

### 3.4 Resuming — `onboard-session`

At the start of a session, after a break, or after your agent's context is reset, **`onboard-session`** re-reads the state: the latest calibration log, the current round's position, live HPC jobs, and any pending knowledge proposals. Use it whenever you would otherwise ask "where were we?"

### 3.5 Driving the loop — `calibration-goal` and the phase skills

**`calibration-goal`** is the run-to-convergence driver: it loads the offline workflow state, resolves the next action, dispatches to the matching phase skill, advances the state, and repeats across turns and HPC waits until Phase 7 or a loop limit — pausing only at the human gates (a Phase-6 converge/redesign decision, a curated-knowledge write, an expensive or irreversible action). **`calibration-discipline`** is the per-cycle checklist that keeps a long campaign stable, and **`round-housekeeping`** closes out a round before the next Phase 0.

Each phase also has its own skill, usable directly when you want to run one step yourself:

| Phase | Skill | Does |
|---|---|---|
| 0 | `phase0-design` | sample the parameter space, materialize parameter files, submit + monitor the ensemble |
| 1 | `phase1-exploration` | extract the Y matrix, run the sensitivity analysis, interpret μ* |
| 2 | `phase2-screening` | rank the ensemble against validation targets |
| 3 | `phase3-diagnosis` | root-cause the failing targets |
| 4 | `phase4-hypothesis` | generate hypotheses; skip-test on existing data before spending HPC |
| 5 | `phase5-testing` | run the designed experiments |
| 6 | `phase6-refinement` | evaluate, extract lessons, decide converge / iterate / redesign |

Supporting skills you will reach for around them: **`arm-hpc-monitoring`** (watch an in-flight ensemble), **`restart-failed-jobs`** and **`restart-adapter-ensemble`** (recover failed runs — the second is the non-CIME analog), **`offline-testing-workflow`** (design and launch a parameter sweep), **`summarize-calibration-round`**, **`compare-calibration-rounds`** and **`write-report`**.

Each adapted model also ships a run-workflow skill carrying the traps that have already cost real compute on that model: **`ecosim-run-workflow`**, **`pflotran-run-workflow`**, **`ats-run-workflow`**.

### 3.6 Recording the work — `calibration-log`

The offline agent writes to the same site log tree the autonomous agent does, so both modes' records synthesize together. **`calibration-log`** writes either a phase log (via `PhaseLogger`) or a free-form session log under `use_cases/<Model>_<Case>/memory/logs/`, with durable artifacts — scripts, figures, manifests — in the paired `phase_results/<stem>/` folder.

### 3.7 Curated knowledge is human-gated

The autonomous loop **cannot** write curated knowledge; it stages proposals to `auto_discovered_pending.json`. Promoting them is an offline, human-reviewed step:

- **`curate-knowledge`** — review the run's staged proposals, promote the vetted ones, discard misunderstandings.
- **`inject-knowledge`** — add a discovery of your own (from a paper, or your own analysis) so the reasoning pipeline surfaces it.

This gate is why unattended runs cannot contaminate the knowledge base. See Section 8.

### 3.8 What the agent tracks between sessions

**`use_cases/<Model>_<Case>/memory/workflow_state_offline_r{RR}.json`** is the per-round resume brain: the position in the loop, open threads with their next action, the Phase-6 objective gate, and per-round evidence pointers. Validate it before acting on it:

```bash
python3 tools/check_workflow_state_offline.py
```

> A stored `next_action` is a **lead to verify, not an instruction to run**. It records what was true when it was written; the artifacts on disk are what is true now.

---

## 4. Using the online (autonomous) agent

```bash
# Source the site config -- the whole chain, before every run (why: section 2)
source use_cases/YourSite/config/yoursite_config.sh
print_config  # Verify settings

# Start a new calibration run (with human review checkpoints between phases)
python orchestrator.py --run

# Run fully autonomous (no interactive prompts)
python orchestrator.py --run --no-review

# Start from a specific phase and calibration round
python orchestrator.py --run --start-phase 2 --start-round 2

# Resume from a saved checkpoint (state-file auto-detected from config)
python orchestrator.py --resume

# Resume Phase 5 after HPC experiments complete, continuing the same session
# (checks job status, extracts results, evaluates, then proceeds to Phase 6)
python orchestrator.py --resume --start-phase 5 --session-id 20260331_030000

# Re-run from Phase 2 using the same session's Phase 1 results
# (backs up state file and downstream phase_results, then re-runs Phase 2+)
python orchestrator.py --resume --start-phase 2 --session-id 20260405_145259
```

`--start-phase` accepts a number, `phaseN`, or the phase name (`exploration`). Use `screen` or `tmux` for long-running HPC sessions. All screen output is saved to `use_cases/{site}/a2mc_run_{timestamp}.log`:

```bash
tail -f use_cases/ELM-FATES_Kougarok/a2mc_run_*.log
```

---

## 5. The 7-phase workflow in detail

A2MC uses a 7-phase workflow with intelligent iteration paths to minimize HPC cost while maximizing learning.

### 5.1 Phase overview

| Phase | Name | Purpose | AI API call (online loop)? | Scripts |
|-------|------|---------|------------|---------|
| 0 | DESIGN | Morris/Sobol sampling, create cases, submit to HPC | Yes | `create_morris_ensemble.py` |
| 1 | EXPLORATION | Extract Y matrix, run sensitivity analysis | **Yes** | `extract_sensitivity_outputs.py`, `morris_sensitivity_analysis.py` |
| 2 | SCREENING | Rank ensemble by validation targets | Yes | `screen_ensemble.py` |
| 3 | DIAGNOSIS | Root cause analysis, edge case detection | Yes | `run_diagnosis.py` (+ 11 diagnostic tools) |
| 4 | HYPOTHESIS | Generate testable hypotheses, then design experiments OR test them on existing data | Yes | `reasoning/`, `phases/phase4_hypothesis/` |
| 5 | TESTING | Run designed experiments on HPC | No | `submit_experiments.py` (+ design, monitor) |
| 6 | REFINEMENT | Evaluate results, extract lessons, check equifinality | Yes | `reasoning/`, `phases/phase6_refinement/` |
| 7 | CONVERGED | Final optimal configuration | - | - |

**What the last column means.** It marks whether the **online** agent (`orchestrator.py --run`) makes an **AI API call** in that phase, which is not the same as whether the phase is AI-driven. **Offline, every phase is agent-driven** — the interactive agent reasons through Phase 5 as much as any other, designing the variants, verifying the parameter files, deciding what to submit and reading the census (`phase5-testing` / `offline-testing-workflow`). Phase 5 is marked "No" only because the online loop reaches it with the experiment already designed in Phase 4, so it executes rather than re-reasons. Same for the "[HPC Wait]" row where one appears: waiting needs no API call, and monitoring it offline is still judgement.


**Phase 3 diagnostic tools:** `analyze_carbon_balance.py`, `analyze_mortality.py`, `analyze_nutrient_balance.py`, `analyze_nutrient_pools.py`, `check_edge_parameters.py`, `compare_case_parameters.py`, `compare_targets.py`, `detect_collapse.py`, `diagnose_pft_limitations.py`, `read_case_parameters.py`, `test_hypothesis_framework.py`.

**Self-improving diagnostic library.** When no existing tool can test a hypothesis, the agent writes a custom `test_*.py` (exposing `test_hypothesis()`) into `phases/phase3_diagnosis/generated/`, auto-discovered for the current run. A vetted, reusable one is then **promoted** into the permanent tool library with `tools/promote_diagnostic_script.py` (copies it to `phases/phase3_diagnosis/` and registers it in the diagnostic-tools inventory; human-gated).

**Phase 5 scripts:** `design_experiments.py`, `monitor_experiments.py`, `submit_experiments.py`.

### 5.2 Iteration paths

A2MC supports non-linear iteration to avoid unnecessary HPC computation:

```
Normal Flow:
  Phase 0 -> [HPC] -> Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> [HPC] -> Phase 6 -> Phase 7

Iteration Paths:
  Phase 4 -> Phase 3: Skip testing when existing data can test the hypothesis
  Phase 6 -> Phase 3: Rethink hypothesis when experiment results disprove it
  Phase 6 -> Phase 0: Redesign when parameter space needs expansion
```

- **Phase 4 -> Phase 3 (skip testing):** when a hypothesis can be tested using existing ensemble data (e.g., P mass balance analysis, comparing PFT responses), skip the HPC testing phase and return to diagnosis with new insights.
- **Phase 6 -> Phase 3 (rethink hypothesis):** when experiment results disprove the hypothesis, return to diagnosis to revise understanding and generate new hypotheses.
- **Phase 6 -> Phase 0 (redesign):** when all parameter candidates are at bounds and calibration fails, expand parameter ranges and run a new ensemble.

### 5.3 Three-level iteration structure

Three nested loops (outermost -> middle -> inner):

**Calibration Round (outermost):** full Phase 0 -> 7 cycle. Counter: `calibration_round`.
- Round 1: e.g., 138 parameters, 4170 simulations.
- Round 2: e.g., 162 parameters, 4890 simulations (expanded parameter space).
- Incremented when Phase 6 -> Phase 0 redesign is needed (experiment cycles reach max without meeting all targets).

**Middle Loop (experiment cycle):** Phase 3 -> 4 -> 5 -> 6 -> 3, max 10 cycles. Counter: `experiment_count`.
- Run full HPC experiments to test hypotheses.
- Exit when targets met (-> Phase 7 CONVERGED) OR experiment cycles reach max (-> Phase 0 redesign).

**Inner Loop (skip testing):** Phase 3 <-> 4, max 10 cycles. Counter: `skip_testing_count`.
- Test hypotheses with existing ensemble data (no HPC cost).
- Exit when confidence threshold met OR max cycles reached.
- Counter resets when entering Phase 5 (HPC).

```bash
# Control iteration limits
python orchestrator.py --run \
    --start-round 2 \              # Calibration round (outermost loop)
    --max-skip-testing 10 \        # Max Phase 3<->4 cycles (default: 10)
    --max-experiments 10 \         # Max full experiment cycles (default: 10)
    --confidence-threshold 0.95    # Exit skip testing threshold (default: 0.95)
```

### 5.4 Phase details

**Phase 0: DESIGN** — create the initial parameter sampling design and submit to HPC. Morris method: `n_trajectories × (n_params + 1)` simulations (e.g., 30 × 163 = 4890). Outputs: Morris ensemble matrix (X matrix) at `phases/phase0_design/FATES_*_Morris_*sets.txt`, modified parameter files per ensemble member, HPC jobs submitted.

**Phase 1: EXPLORATION** — extract the Y matrix (model outputs) from completed simulations, run Morris sensitivity analysis (SALib), rank parameters by μ* (mean absolute effect) and σ (interaction effect), generate plots and CSV rankings. Outputs: Y matrices (`MorrisLeafbiomass_*.txt`, etc.), per-PFT sensitivity rankings, sensitivity plots.

**Phase 2: SCREENING** — rank ensemble members against validation targets. Calculate cost metrics (RMSRE, NRMSE) across all targets, rank by multi-objective performance, identify met/failed targets per case, detect edge cases (parameters at bounds). Outputs: ranked case list with composite cost, per-target error statistics, edge parameter analysis.

**Phase 3: DIAGNOSIS** — root cause analysis of calibration failures. The AI analyzes which targets are failing and why, identifies mechanistic causes (e.g., P-limitation, allocation issues), finds cross-PFT parameter conflicts, compares best vs worst cases, and generates parameter adjustment recommendations. Output: diagnosis report with root causes, affected mechanisms, and priority rankings.

**Phase 4: HYPOTHESIS** — generate testable hypotheses. The AI creates named hypotheses (e.g., "PFT10 P-starvation hypothesis"), specifies parameters to modify and expected direction, defines expected outcomes and success criteria, and chooses an approach: run new experiments, or test with existing data. Output: hypothesis with modification plan or analysis plan.

**Phase 5: TESTING** — run designed experiments on HPC. Create modified parameter files, submit experiment simulations, extract and evaluate results, compare actual outcomes to expected.

**Phase 6: REFINEMENT** — evaluate results and extract lessons. Decision logic: hypothesis confirmed -> apply changes, check remaining targets; partially confirmed -> adjust hypothesis, return to Phase 4; rejected -> record failed approach, return to Phase 3; all targets met -> advance to CONVERGED; parameter bounds too restrictive -> return to Phase 0 (redesign). Adaptive Memory learning: extract lessons, store discoveries in `gained_knowledge/discoveries.json`, record failed approaches in `gained_knowledge/failed_approaches.json`, update parameter knowledge, check for equifinality.

**Phase 7: CONVERGED** — finalize calibration. Outputs: best parameter configuration, final calibration report, complete experiment history, extracted knowledge for future calibrations.

### 5.5 Validation targets

Validation targets are site-specific and defined in `use_cases/{site}/README.md`. Typical types: biomass (leaf, fine root, AGB by PFT, g C/m²), ecosystem fluxes (GPP, NPP, NEE, g C/m²/yr), structure (LAI, canopy height), phenology (leaf-on/off dates). See `use_cases/ELM-FATES_Kougarok/README.md` for a complete target specification.

---

## 6. Module reference

### 6.1 orchestrator.py

Main workflow controller with state persistence. Configuration is loaded from environment variables set by `a2mc_config.sh` and site config.

```python
from orchestrator import CalibrationOrchestrator, Config

# Config auto-detects paths from A2MC_USE_CASE_DIR environment variable
config = Config(
    use_memory=True,           # Enable Adaptive Memory
    use_reasoning=True,        # Enable Claude API reasoning
    max_iterations=10,
    max_skip_testing=10,       # Max Phase 3<->4 skip testing cycles
    max_experiments=10,        # Max Phase 3->4->5->6 experiment cycles
)
orch = CalibrationOrchestrator(config)
orch.run()
```

Key classes: `Config` (all settings), `Phase` (enum of 8 workflow phases), `WorkflowState` (persistent state with full history), `CalibrationOrchestrator` (main controller).

### 6.2 reasoning/ package

Claude API interface for intelligent reasoning (split into `schemas.py`, `prompts.py`, `base.py`, `methods.py`, `validation.py`).

```python
from reasoning import ReasoningModule, Diagnosis, Hypothesis

reasoning = ReasoningModule()

diagnosis = reasoning.diagnose(
    results={"leaf_pft10": 45.2, ...},
    targets={"leaf_pft10": {"mean": 82.7, "uncertainty": 0.20}, ...},
    sensitivity_rankings={"leaf_pft10": [{"param": "...", "mu_star": 0.45}]},
    iteration=1
)

hypothesis = reasoning.generate_hypothesis(
    diagnosis=diagnosis,
    sensitivity_data={...},
    previous_experiments=[]
)

experiments = reasoning.design_experiments(
    hypothesis=hypothesis,
    base_case={"case_id": 2678, "parameters": {...}}
)

interpretation = reasoning.interpret_results(
    experiment=experiments[0],
    actual_results={...},
    targets={...}
)
```

Output structures: `Diagnosis` (failing targets, causes, parameter/protocol recommendations, requested diagnostics), `Hypothesis` (name, mechanism, parameter modifications, test plan), `Experiment` (base case, modifications, expected results).

### 6.3 tools/hpc_utils.py

HPC-native interfaces for simulation management.

```python
from tools.hpc_utils import HPCConfig, HPCExecutor, ParameterManager

config = HPCConfig()  # reads from A2MC_* environment variables

param_mgr = ParameterManager(config)
new_param_file = param_mgr.create_modified_file(
    base_file="fates_params.nc",
    modifications=[
        {"parameter": "fates_alloc_storage_cushion", "pft": 10, "value": 3.0}
    ],
    output_file="fates_params_modified.nc"
)

executor = HPCExecutor(config)
job_id = executor.submit_case(case_name="PtCNPEn100_TRANS")
results = executor.wait_for_jobs([job_id], poll_interval=300)
```

Key classes: `HPCConfig` (HPC paths, project, QOS from env vars), `HPCExecutor` (direct sbatch/squeue execution), `ParameterManager` (wraps `modify_fates_parameters.py`).

---

## 7. Knowledge system

### 7.1 Three-tier FATES knowledge

Same knowledge encoded in three tiers so the AI can reach it via multiple retrieval paths:

| Tier | Location | Format | Purpose |
|------|----------|--------|---------|
| **Static Documentation** | `docs/fates-knowledge-base/` (per-commit subdirs) | Markdown | Human reference, RAG indexing |
| **RAG/GraphRAG** | `rag/{chroma_db,graphs,metadata}/<profile>/` | ChromaDB + JSON graph | AI semantic search, graph traversal — version-aware (per-milestone) and configuration-aware (per simulation mode) |
| **Adaptive Memory** | `memory/gained_knowledge/` | JSON | AI reasoning context, learned discoveries |

Key resources for CNP calibration:
- **START HERE:** `docs/fates-knowledge-base/fates-codebase-wiki/advanced/cnp_calibration_guide.md` (Knox 2026)
- PID controller: `docs/fates-knowledge-base/fates-codebase-wiki/plant-physiology/parteh/cnp_allocation.md`
- ECA/RD competition: `docs/fates-knowledge-base/fates-codebase-wiki/advanced/nutrient_competition.md`
- Nutrient uptake: `docs/fates-knowledge-base/fates-codebase-wiki/plant-physiology/parteh/soil_plant_interface.md`

The RAG/GraphRAG tier is **version-aware** (v2.90+), **configuration-aware** (v2.91 / v2.92), and **drift-aware** (v2.98). A2MC auto-detects the user's E3SM/ELM-FATES checkout and the active simulation mode, loads the right knowledge profile, filters out content that does not apply, and (with opt-in) auto-rebuilds the profile when the checkout drifts off the matched milestone.

### 7.2 Version association (v2.90)

A2MC reads the user's `A2MC_MODEL_PATH` (E3SM checkout root), detects the FATES + ELM commit hashes, and matches against the milestone registry at `rag/milestones.json`. Each milestone owns a self-contained profile: ChromaDB index, NetworkX graph, metadata, and a frozen per-milestone curated YAML.

| Milestone | FATES tag | FATES commit | ELM commit | Param file | Status |
|---|---|---|---|---|---|
| `api-43-1` | `sci.1.91.1_api.43.1.0` | `e027a40` | `d40b843` | JSON | Canonical (active development) |
| `api-31-0` | `sci.1.68.2_api.31.0.0` | `e85d997` | `60d9aad` | CDL | Legacy / Kougarok manuscript reproducibility |

```bash
# A2MC auto-detects on startup, picks the right RAG profile, and aligns or warns
export A2MC_MODEL_PATH="/path/to/your/E3SM_FATES_checkout"
source use_cases/ELM-FATES_Kougarok/config/kougarok_config.sh   # auto-sources a2mc_config.sh
python orchestrator.py --run
```

Diagnostic CLIs:

```bash
python scripts/rag_list.py                                     # List registered milestones
python scripts/rag_match.py --model-path /path/to/E3SM_FATES   # Which milestone matches a checkout
python scripts/rag_bump.py --tier T2 --new-version sci.1.91.4_api.43.1.0 --mode prompt-pack
python scripts/verify_phase4.py                                # 24 content gates + 9 smoke tests
```

Per-milestone YAML reproducibility: each milestone owns `rag/data/curated_relationships_<profile>.yaml`. Rebuilding a milestone always uses its frozen YAML, preventing silent corruption when the canonical evolves. Full workflow: `docs/a2mc_reference/version_association_workflow.md`.

### 7.3 Configuration-aware retrieval (v2.91 / v2.92)

A2MC parses the user's `A2MC_ELM_OPTIONS` and Tier 2 env vars into a 20-dimension `ConfigMode`. The RAG retriever builds a ChromaDB `where` clause from this and filters every chunk: PARTEH=1 retrieval no longer surfaces CNP allocation theory, fire chunks are filtered when SPITFIRE is off, ELM-only runs see only ELM content.

**The 20 dimensions** (defaults match ELM `namelist_defaults.xml` — a vanilla SP run):

- **Tier 1 primary (7):** `bgc_mode` (sp/cn/bgc/fates), `use_fates` (derived), `parteh_mode` (1=carbon-only / 2=CNP), `use_fates_nocomp`, `nutrient` (c/cn/cnp), `nutrient_comp_pathway` (rd/eca), `soil_decomp` (ctc/century)
- **Tier 2 FATES feature flags (6):** `fates_spitfire_mode`, `use_fates_planthydro`, `use_fates_logging`, `use_fates_sp`, `use_fates_ed_prescribed_phys`, `use_fates_fixed_biogeog`
- **Tier 3 secondary compset modifiers (7):** `crop`, `dynamic_vegetation`, `methane`, `hydrstress`, `topounit`, `irrig`, `solar_rad_scheme`

Three independent metadata sources tag chunks during the build: (1) YAML curation via `applies_in:` blocks on parameters/mechanisms/outputs (17 mode-restricted parameters + 3 mechanisms tagged in the canonical YAML); (2) a path-prefix table of 11 patterns covering 22+ wiki docs in `rag/loader.py:_WIKI_PATH_PREFIX_TAGS` (including inverse-tagged docs, e.g., `biophysics/transpiration.md` applies when hydraulics is OFF); (3) a default-permissive sweep marking any untagged chunk/node `applies_universal: True`.

```bash
# Example config: Kougarok PARTEH=2 + ECA + CNP
export A2MC_ELM_OPTIONS="-bgc fates -nutrient cnp -nutrient_comp_pathway eca"
export A2MC_FATES_PARTEH_MODE=2
# Optional Tier 2 (default off):
# export A2MC_FATES_SPITFIRE_MODE=1
# export A2MC_USE_FATES_PLANTHYDRO=true
```

The reasoning module reads `ConfigMode.from_env()` once per Phase 3/4 retrieval call and threads the where clause through `HybridRetriever.get_targeted_context()`, `get_calibration_context()`, and `get_context()` to the ChromaDB layer.

### 7.4 Auto-rebuild on drift (v2.98)

When the orchestrator's startup hook detects that the checkout has drifted off the matched milestone, it dispatches via `tools/auto_rebuild.py:handle_drift()` per the tier policy:

| Tier | Condition | Action | Flag-gated? |
|---|---|---|---|
| **T1** | No drift, all SHAs match | In-process metadata refresh via `tools/rag_refresh.py` | No (always auto) |
| **T2** | Same epoch, FATES parameter file SHA differs | Subprocess `rag_bump.py --mode auto` + validator gate; rollback to `<profile>.previous/` on Red | Yes (`A2MC_RAG_AUTO_REBUILD=true`) |
| **T3-near** | `epoch_distance ≤ A2MC_RAG_T3_AUTO_DISTANCE` (default 100) | Same as T2 (full pipeline) | Yes |
| **T3-distant** | `epoch_distance > A2MC_RAG_T3_AUTO_DISTANCE` | Always emit prompt-pack at `Offline/bump_pack_<target>/` and abort startup | No (always manual) |

`epoch_distance` formula: `|major_a − major_b| × 100 + |minor_a − minor_b|`. So api-43-1 -> api-44-0 = 100 (auto-eligible); api-31-0 -> api-43-1 = 1201 (always manual). Concurrency is enforced by a file lock at `<rag_dir>/.bump.lock`. A Red verdict triggers automatic rollback to `<profile>.previous/`; the broken build is preserved at `<profile>.failed_<UTC-timestamp>/` for forensics. End-user how-to: `docs/a2mc_reference/version_association_howto.md` "Drift handling".

### 7.5 Validation — five layers

The knowledge-build validation started as a three-tier triangle (codebase_wiki + yaml_wiki + rag_diff), gained Tier 4 for mode-metadata propagation in v2.92, and added three more validators in v2.95:

| Layer | Validator | Asserts |
|---|---|---|
| **Tier 1** | `tools/codebase_wiki_validator.py` | Wiki claims match source (per-commit) |
| **Tier 2** | `tools/yaml_wiki_validator.py` (incl. Dim F for `applies_in:`) | Curated YAML entries present in wiki + parameter file; mode tags valid |
| **Tier 3** | `tools/rag_diff.py` | Diff between two RAG profiles (e.g., milestone bump) |
| **Tier 4** | `tools/mode_metadata_validator.py` (v2.92) | YAML `applies_in:` propagates correctly to chunks + graph nodes |
| **Snapshot** | `tools/snapshot_validator.py` (v2.95) | End-to-end integration test across 5 fixture ConfigModes |
| **Profile completeness** | `tools/profile_completeness_validator.py` (v2.95) | 5-category statistical coverage |
| **Cross-milestone** | `tools/cross_milestone_validator.py` (v2.95) | `applies_in:` drift between milestone YAMLs |

```bash
# Unified harness — runs all five layers + the orchestrator-side gate (v2.98)
python scripts/verify_mode_aware.py     # Verdict: GREEN

# Per-layer validators all have standalone CLI entry points; see
# docs/a2mc_reference/rag_validation_workflow.md for the full playbook.
```

The same `run_all_validators(profile)` function gates the v2.98 auto-rebuild path; a Red verdict triggers automatic rollback.

### 7.6 Reference docs

- **Comprehensive mode-aware workflow:** `docs/a2mc_reference/mode_aware_workflow.md`
- **Mode-aware quick how-to:** `docs/a2mc_reference/mode_aware_howto.md`
- **ELM compset reference:** `docs/a2mc_reference/elm_compset_reference.md`
- **Version association workflow / how-to:** `docs/a2mc_reference/version_association_workflow.md`, `version_association_howto.md`
- **Validation playbook:** `docs/a2mc_reference/rag_validation_workflow.md`
- **RAG system reference:** `docs/a2mc_reference/rag_reference.md`
- **RAG from-scratch reconstruction:** `docs/a2mc_reference/rag_build_roadmap.md`

---

## 8. Adaptive Memory system

Two-tier knowledge architecture enabling learning across sessions while keeping site-specific knowledge separate.

```
GENERIC KNOWLEDGE (memory/gained_knowledge/)
  General FATES mechanistic insights; applies to all sites

SITE-SPECIFIC KNOWLEDGE (use_cases/{model}_{site}/memory/)
  Site-specific discoveries and experiments; phase execution logs; lessons learned

KNOWLEDGE PROMOTION
  AI evaluates site-specific discoveries; generalizable lessons promoted to generic knowledge
```

### 8.1 Memory stores

**Generic** (`memory/gained_knowledge/`): `discoveries.json` (general FATES insights), `experiments.json` (generic patterns), `parameters.json` (parameter knowledge), `failed_approaches.json` (approaches to not repeat).

**Site-specific** (`use_cases/{model}_{site}/memory/gained_knowledge/`): `discoveries.json` (e.g., "Kougarok Allocation Paradox"), `experiments.json`, `failed_approaches.json`.

**Phase execution logs** (`use_cases/{model}_{site}/memory/logs/`): `phase2_screening/`, `phase3_diagnosis/`, `phase4_hypothesis/`, `phase6_refinement/` (Markdown, with AI reasoning).

### 8.2 MemoryManager API

```python
from memory import MemoryManager

# Generic knowledge
memory = MemoryManager("memory/gained_knowledge")
# Site-specific knowledge
memory = MemoryManager("use_cases/ELM-FATES_Kougarok/memory/gained_knowledge")

# Query methods
context = memory.get_relevant_context(targets=targets, parameters=parameters)
# NB: there is no `phase=` kwarg — the real signature is
#   get_relevant_context(failing_targets=None, max_chars=8000, targets=None,
#                        parameters=None, verified_only=False)
failed = memory.get_failed_experiments(parameters)
knowledge = memory.get_parameter_knowledge("fates_alloc_storage_cushion")
stats = memory.stats()

# Update methods
memory.record_experiment(experiment_id, base_case, modifications, results, outcome)
memory.add_discovery(name, description, mechanism, affects, confidence)
memory.add_failed_approach(approach, experiment_id, why_failed, severity, alternatives)
memory.update_parameter_knowledge(param_name, knowledge)
```

### 8.3 Knowledge in AI prompts

When A2MC performs diagnosis or generates hypotheses, three knowledge sources are combined into the prompt:

| Source | Content | Role |
|--------|---------|------|
| **RAG/GraphRAG** | model source documentation | General knowledge ("how does the PID controller work?") |
| **Adaptive Memory** | Discoveries, failed approaches, parameter insights | Learned knowledge ("what failed before? what worked?") |
| **Calibration Memory** | Logs, reports, phase results, targets, sensitivity rankings | Current context ("what are we calibrating?") |

Prompt structure (in order): RAG/GraphRAG context -> Adaptive Memory context (failed approaches marked "DO NOT REPEAT") -> current data -> task instructions + response format. The sources are complementary, not strictly prioritized: RAG provides "textbook" knowledge, memory provides "experience," and both inform reasoning over the current task data.

### 8.4 Referencing knowledge from similar sites

| Your site type | Reference site | Transferable knowledge |
|----------------|----------------|------------------------|
| Arctic/tundra | `use_cases/ELM-FATES_Kougarok/` | Allocation Paradox, P-limitation dynamics, graminoid-shrub competition |
| CNP-enabled | `use_cases/ELM-FATES_Kougarok/` | PID controller behavior, ECA competition, vmax calibration strategies |

What transfers: mechanistic insights, diagnostic patterns, failed approaches. What does not: exact parameter values (site-specific).

```python
from memory import MemoryManager
kougarok_memory = MemoryManager("use_cases/ELM-FATES_Kougarok/memory/gained_knowledge")
discoveries = kougarok_memory.discoveries.get('discoveries', [])
failed = kougarok_memory.failed_approaches.get('failed_approaches', [])
```

### 8.5 Seeding memory

```bash
cp scripts/curated_knowledge_template.yaml scripts/curated_knowledge.yaml
# Edit with your discoveries, then:
python scripts/seed_memory_from_yaml.py --input scripts/curated_knowledge.yaml
```

---

## 9. Experimental design strategies

**Cumulative design** — test parameters sequentially, adding one at a time. Use when parameters act through sequential mechanisms (A -> B -> C).

```
Exp1: param_A only
Exp2: param_A + param_B
Exp3: param_A + param_B + param_C
```

**Factorial design** — test all combinations. Use when parameters may interact (synergistic or antagonistic effects).

```
Exp1: param_A=low,  param_B=low
Exp2: param_A=low,  param_B=high
Exp3: param_A=high, param_B=low
Exp4: param_A=high, param_B=high
```

---

## 10. State persistence

All workflow state is saved to JSON for resumability:

```json
{
  "phase": "DIAGNOSIS",
  "iteration": 3,
  "start_time": "2025-01-06T10:30:00",
  "config": {
    "work_dir": "<your scratch>/A2MC",                       # e.g. /pscratch/sd/<i>/<user>/A2MC
    "param_file": "fates_params.nc",
    "output_root": "<shared project space>/A2MC_runs"        # e.g. /global/cfs/cdirs/<project>/<user>/A2MC_runs
  },
  "design": {
    "method": "morris",
    "n_params": 162,
    "n_trajectories": 30,
    "n_samples": 1000,
    "total_ensemble": 4890
  },
  "screening": {
    "top_cases": [2678, 845, 3930],
    "best_composite_nrmse": 0.493
  },
  "experiments": [
    {
      "name": "Exp1_storage_cushion",
      "base_case": 2678,
      "modifications": [],
      "results": {},
      "interpretation": {}
    }
  ],
  "phase_history": [
    {"phase": "DESIGN", "completed": "2025-01-06T11:00:00"},
    {"phase": "EXPLORATION", "completed": "2025-01-08T14:30:00"}
  ]
}
```

---

## 11. Integration with existing tools

A2MC wraps existing well-tested tools rather than reimplementing:

**Parameter modification** (`modify_fates_parameters.py`): `create_modified_parameter_file(input, output, modifications)`; handles 1D/2D parameters; supports absolute values or percent changes; verifies modifications after applying.

**Data extraction** (`extract_monthly_variables_FATES.py`): extracts site-, PFT-, and SZPF-level variables; outputs NetCDF (all vars) + CSV (site/PFT only); processes yearly files (12 months each); ~50-100× faster than daily extraction.

**Job submission** — direct SLURM commands: `sbatch case.submit`, `squeue -u $USER`, `scancel job_id`, `sacct -j job_id --format=...`.

---

## 12. Error handling

What the workflow handles on its own:
- **API errors:** rate limiting with automatic backoff, fallback to rule-based reasoning if the API is unavailable, repeated queries cached to reduce cost.
- **Missing data:** verify expected files before proceeding, clear error messages with suggested fixes, option to skip incomplete cases.

### Handling job failures — the recovery skills

Past those automatic paths, recovery is the offline agent's job (Section 3), and each failure shape has a skill that carries the traps rather than leaving you to rediscover them:

- **`arm-hpc-monitoring` — arm this when you launch, not when you suspect trouble.** It detects the live long-running processes (submitter, extractor, watcher) and arms a watch on each log with an event *and* error filter. The rule it exists to enforce is that **silence is not success**: a log that stops growing is byte-identical whether the job is running quietly or died, so the watch needs a progress signal, an error pattern, and a liveness **heartbeat** (`python3 tools/check_watcher_state.py`) that fails loudly when the watcher itself dies. A finished ensemble once sat unnoticed for about 19 hours because only the first two were in place.
- **`restart-adapter-ensemble` — recovery for a non-CIME ensemble (EcoSIM, PFLOTRAN, ATS).** Classifies *why* each case died, persists the failed-case list, and relaunches only what is missing. Run it before any sensitivity analysis: a crashed case is a **hole in the sampling design**, which is a different problem from a case that finished with a degenerate answer, and Morris or Sobol indices computed over holes are not trustworthy.
- **`restart-failed-jobs` — the CIME / ELM-family counterpart.** Its central judgment is that **infrastructure failures are restart-eligible and model failures are not**: a node failure or a down partition can simply be resubmitted, while a mass-balance abort or a runaway-recruitment crash will reproduce exactly until a parameter or the model changes. The reasoning transfers to any model; the scripts do not, since they assume CIME's submission path — on a non-CIME model use `restart-adapter-ensemble` above.
- **`diagnose-forensics` — for a result that looks wrong rather than a job that failed.** Establishes first whether the anomaly is real or an artifact of extraction, units, or the plot, and only then root-causes it. Worth reaching for before you change a parameter in response to something that may not be in the model at all.

`tools/diagnose_ensemble_status.py` underlies the completion census that the two restart skills read, and is worth running directly whenever you just want to know how many cases finished.

---

## 13. Cost management

**Claude API usage** (per call): diagnosis ~2K in / ~1K out; hypothesis ~3K in / ~1K out; experiment design ~2K in / ~500 out; interpretation ~2K in / ~1K out. Estimated cost per iteration: ~$0.10-0.20 (Sonnet).

**HPC resources:** Morris ensemble (4890 sims) ~50K node-hours; single experiment ~10 node-hours; data extraction ~0.1 node-hours per case.

---

## 14. Calibration logs, cycle reports, and round reports

Calibration work is recorded at three nested timescales, each with an owning skill and its own audience. Getting these right is what lets a round be picked up months later, by you or by someone else, without re-deriving why it went the way it did.

| record | one per | lives in | written by | read by |
|---|---|---|---|---|
| **phase log** + paired artifact folder | phase | `memory/logs/` + `memory/phase_results/` | `calibration-log` | you, the next session, the agent |
| **cycle report** | experiment cycle (Phase 3→4→5→6) | `reports/<stem>/` | `write-report` | the project team |
| **round report** | calibration round (Phase 0→7) | `reports/<stem>_R{N}_ROUND_SUMMARY/` | `write-report`, after two required skills | the project team, the next round's design |

Logs are the internal working record and may use shorthand. Reports are written for a reader with **zero project context** and must define their own terms.

### 14.1 The phase log and its paired artifact folder

The interactive agent writes a **flat, date-led stem** — `memory/logs/{stem}.md` where `stem = YYYYMMDDx_phase{N}_{name}_r{RR}[_c{EE}[_iter{II}]]_{descriptor}` — with `RR` the calibration round, `EE` the experiment cycle and `II` the skip-testing iteration. Set `A2MC_AGENT_MODE=offline` to select it. The autonomous orchestrator uses a different layout for the same content, nesting under `memory/logs/{session_id}/phase{N}_{name}/`; both are folded together for synthesis, so the two agents' records read as one history.

Every log has a paired artifact folder at `memory/phase_results/{stem}/`, and **the two have different jobs**:

- **The log carries the ANALYSIS** — the reasoning, the numbers with their interpretation, the conclusion, and the next action. Not a caption dump: the argument a cold reader has to be able to reconstruct.
- **The artifact folder is SELF-DOCUMENTING** — for each figure it ships four things: the figure, a caption or `NOTES.md` (what it shows, how to read it, and which script produced it from what data), the generating `.py` script saved into the folder, and the underlying data file. A future reader must be able to regenerate and interpret the figure without you.

Two mechanics that are easy to get wrong:

- **The log must EMBED its figures, not merely name their folder.** A path in backticks renders as text and sends the reader hunting. Use `![](../phase_results/{stem}/figure.png)` with empty alt text and a bold `**Figure N.**` caption beneath that states the finding rather than the axes; the relative path resolves in-repo. `python3 tools/check_offline_log_evidence.py` warns when the folder holds a figure the log does not embed.
- **The log and the folder pair only if both derive from the same string.** Pass the same `TITLE` to `topic_artifact_dir()` and to `log_<phase>()`; two different descriptors produce two stems and a log that does not match its own artifacts.

Conformance is checked by `python3 tools/check_calibration_log_conformance.py`, which is a different contract from the framework-development log checker and refuses the other's stream rather than mis-checking it.

### 14.2 The cycle report

Written when an experiment cycle closes, into `reports/<stem>/`, alongside the figures it cites. Four things it must carry, each of which was added because a real report omitted it:

1. **The whole inner loop, iteration by iteration** — Phase 3↔4 skip-testing runs several times within one cycle, each iteration asking something and answering it on existing data at no compute cost. Those answers are what justify the experiment the cycle finally ran, so a report naming only the surviving hypothesis leaves a reader unable to tell a well-aimed experiment from a lucky one.
2. **Every hypothesis, with its falsification bar** — the bar as Phase 4 recorded it, the variants that tested it with their actual parameter values, and the job identifiers. A verdict whose bar is not restated has to be taken on trust.
3. **What the results say per variant and per SCORED target**, against the measurements — not one composite score, and not one target out of several. An experiment that hits the target it aimed at while pushing two others out of band has failed, and a single-target figure cannot show that.
4. **The verdict and where the loop goes next, with the reasoning that sends it there** — CONFIRMED / PARTIAL / REFUTED against the Phase-4 bar, the mechanism learned, and the routing (rethink 6→3, redesign 6→0, or converge). On a rethink, carry the lever-class verdict, any direction still untested, and the new pathways with their falsifiers: a reader who cannot see why the next cycle attacks what it attacks cannot distinguish a redirected campaign from a stalled one.

### 14.3 The round report

Written when the round closes, at the cycle limit or at convergence. It covers what Phases 0, 1, 2 and the first diagnosis established, then **synthesizes the cycle reports** into the round's arc: which levers were established and which retired, what each cycle's failure taught the next, and the residual gap. It cites the cycle reports rather than re-narrating them from raw logs, and it ends with the **next round's work plan** — parameters to add or drop, bounds to revisit, whether the base case should be updated.

**Two skills run before it is written, and they are steps rather than suggestions:**

1. **`summarize-calibration-round`** — the standardized single-round bundle: the whole-ensemble figure per scored target, an evaluation report (best case, how many targets met, per-target simulated versus observed against each target's own band), and the round's sensitivity screen. Its output is the round report's figure and evaluation input. The contract is model-agnostic; the backend is per model.
2. **`compare-calibration-rounds`** — the cross-round **parameter ledger**: what every round did with each parameter, whether calibrated, refuted with a named mechanism, baked into the base, never present, or still carrying provisional bounds. **This is the step that gets skipped and must not be.** A round report written from this round's artifacts alone will re-propose a lever an earlier round already refuted; that has happened, twice in one summary, and every checker passed because nothing in the round-close path opens a prior round.

**A sensitivity figure and its discussion are required whatever the sampling method used.** A round whose designed estimator failed to converge does not get to omit the section; it falls back to the controlled comparisons the round actually produced.

A third stream shares the same stem convention: `memory/model_evolution/{stem}.md` records which model binary a round ran and what changed since the previous round, plus any change made to the model source for this case. It is written at the round close, so the round report carries only a compact pointer instead of putting engineering provenance in the middle of a science narrative.

### 14.4 After the gate — `round-housekeeping`

Between the round's human gate and the next round's Phase 0 sits the step nothing used to schedule: curate the round's Phase-5-verified findings into the case knowledge base, promote or discard the autonomous agent's staged proposals, emit the open-questions list the next round's design must answer, record which bounds are still provisional debt, and assert the knowledge base is non-empty where the round produced findings.

### 14.5 Anything that is not a round close

Use **`write-report`** for an integrated report on any other topic (an investigation, a mechanism study, a cross-cutting result), **`scientific-analysis`** or **`diagnose-forensics`** for an anomaly, **`plotting`** for every figure in any of them, and **`markdown-to-pdf`** to send one outside the repo. Each case's `reports/README.md` carries this routing table for the folder you are standing in.

For slide decks and narrated video built from session logs, the offline presentation pipeline is documented separately in `tools/reports/WORKFLOW.md`.

---

## 15. Directory structure

```
A2MC/
├── README.md              # Front-door overview
├── a2mc_config.sh         # Machine-level configuration (HPC paths, defaults)
├── orchestrator.py        # Main workflow controller
├── reasoning/             # Claude API interface (package)
│   ├── schemas.py         # Diagnosis, Hypothesis, Experiment dataclasses
│   ├── prompts.py         # DIAGNOSTIC_TOOLS_INVENTORY, CUSTOM_SCRIPT_TEMPLATE
│   ├── base.py            # ReasoningModule class core (init, query, RAG)
│   ├── methods.py         # Phase methods (diagnose, hypothesis, etc.)
│   └── validation.py      # Hypothesis validation and AI self-review
│
├── use_cases/             # Site-specific case studies
│   ├── TEMPLATE/          # Template for new sites
│   └── Kougarok/          # Kougarok, Alaska (NGEE-Arctic)
│       ├── config/        # ALL site-specific settings
│       ├── parameters/    # Parameter list + SALib problem
│       ├── validation/    # Validation targets
│       └── memory/        # SITE-SPECIFIC KNOWLEDGE
│           ├── logs/            # Phase execution logs (session-scoped)
│           │   └── {session_id}/phase{2..6}_*/
│           ├── phase_results/   # Phase outputs (session-scoped)
│           ├── extracted/       # Extracted lessons (YAML)
│           └── gained_knowledge/  # discoveries / experiments / failed_approaches (JSON)
│
├── phases/                # Phase-specific scripts (phase0_design … phase6_refinement)
│
├── tools/                 # Shared utilities (config, logging, cost functions,
│                          #   hpc_utils, modify_fates_parameters, extract_knowledge, …)
│
├── memory/                # GENERIC KNOWLEDGE (framework-level)
│   ├── manager.py         # MemoryManager class
│   ├── store.py           # JSON persistence utilities
│   └── gained_knowledge/  # Generic FATES knowledge (JSON)
│
├── rag/                   # RAG/GraphRAG system
│   ├── loader.py, vector_store.py, knowledge_graph.py, graph_builder.py, hybrid_retriever.py
│   ├── data/              # curated_relationships*.yaml (knowledge source of truth)
│   ├── chroma_db/<profile>/, graphs/<profile>.json, metadata/<profile>.json
│   └── milestones.json    # Version registry
│
├── docs/                  # Documentation
│   ├── a2mc_reference/    # Reference docs (this guide, mode-aware, version-association, validation, …)
│   └── fates-knowledge-base/  # FATES documentation (official + wiki)
│
├── scripts/               # Utility scripts (seed_memory, build_rag_index, rag_list/match/bump, …)
│
└── plot/                  # Visualization scripts
```
