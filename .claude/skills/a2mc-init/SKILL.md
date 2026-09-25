---
name: a2mc-init
visibility: public
category: meta
description: First-run interactive setup for the offline agent — the per-CLONE half of getting started, run once when A2MC is first used on a machine or in a fresh clone. Greet and gauge the user's experience, verify the model checkout against the RAG milestone registry, offer fork-safe remotes on that checkout, and write the machine config (a2mc_config.sh for a CIME model, a2mc_noncime_config.sh for a standalone one), then ROUTE onward — to onboard-model for a model A2MC has never seen, or to onboard-case to create the calibration case itself. Use when the user says "set up A2MC", "first time using A2MC", "help me get started / onboard me to A2MC", "configure A2MC on this machine", "wire up my clone", "finish the wire-up steps", "help me finish setting up", or introduces themselves as a new user of this clone. DISTINCT from onboard-session (which resumes an ALREADY-configured setup) and from onboard-case (which creates a case and is repeatable).
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [setup]
  summary: "Per-clone first-run setup: greet -> wire the clone -> (new model: onboard-model) -> verify checkout + RAG milestone -> fork-safe remotes -> machine config -> route to onboard-case / onboard-session."
---

<!-- ───────────────────────── At a glance ───────────────────────── -->
```text
Router  python3 tools/check_stage_ready.py   (per-clone rows + stage + NEXT; nothing to source)
Step 0  greet · name (whoami.py --set) · experience · WHICH model · HPC or workstation
Step 1  wire the clone: setup_clone.sh → check_clone_setup.py exit 0 · GitHub question   ← EVERY user
          └─ model A2MC does not have → Step 3 (machine config) → onboard-model   (this skill ends)
Step 2  the model install on THIS machine, for a model A2MC has
          2.1 get + build from models/<m>/BUILD.md (ELM-FATES: an E3SM checkout) → archive the binary
          2.2 verify: rag_match.py (ELM) · model_preflight.py (others)
                match · DRIFT → proceed, say so · NO MILESTONE → onboard-model · CANNOT VERIFY → 2.1
Step 2b fork-safe remotes: offered; required only before editing model source (onboard-model Step 0b)
Step 3  machine config: (a) a2mc_config.sh for CIME · (b) a2mc_noncime_config.sh otherwise
Step 4  route → onboard-case (a new case) · onboard-session (a running case) · name the model's runbook
          onboard-case owns the interview, research plan (★ GATE 1), parameter list (★ GATE 2),
          check_setup_ready.py and the hand-off to phase0-design
```

# a2mc-init — first-run setup (offline agent)

The **front door** for a new A2MC user. The offline agent (a coding-agent harness opened in the repo) runs this once per clone to turn "I cloned A2MC" into "this clone is wired, my model runs here, and I know which skill builds my case." It greets the user, wires the clone, gets the model built and verified on this machine, writes the machine config, and routes onward. **It does not build a case**: the interview, the research plan, the parameter list and the Phase-0 hand-off belong to `onboard-case`, which runs again for every later case.

**Which setup skill applies — ask the repo, not the conversation.** The stage is read from disk:

```bash
python3 tools/check_stage_ready.py       # needs nothing sourced; prints the per-clone rows and the stage
```

| what it shows | the user wants | skill |
|---|---|---|
| per-clone rows FAIL (`THIS CLONE IS NOT FULLY SET UP` at session start) | anything | **this skill, Step 1**, then continue with what they wanted |
| clone wired, no real case | to calibrate a model A2MC has | **this skill** from Step 2 (the model install), then `onboard-case` |
| any | a model A2MC does not have | **this skill** Steps 0, 1 and 3, then `onboard-model` |
| a case directory with no offline workflow state | to finish it | `onboard-case`, resuming at `check_stage_ready.py --case <Case>`'s first failing row |
| a case with offline workflow state | to continue | `onboard-session` |

This skill is idempotent: a step whose check already passes is confirmed and skipped, never redone.

## Core discipline (read first)

> **Definition of done for this stage: `setup-discipline`.** This skill performs the stage; that one
> collects what "finished" means for it, with the executable gate per item. Check it before
> declaring this stage complete.


This skill writes files and asserts model behavior, so the offline-agent operating discipline applies hard
— the four failure modes + the gate enforcing each are in `AGENTS.md` §"Offline-Agent Operating Discipline"
(lead memory `feedback_offline_agent_operating_discipline`). In this skill that means especially:

- **Anchor every write to the A2MC repo root.** This skill writes only per-clone state (`.me`, the git
  config `setup_clone.sh` sets) and the machine config; the case directory is `onboard-case`'s. Derive the
  root once, since `A2MC_ROOT` is unset until a site config sets it:
  ```bash
  A2MC_ROOT="${A2MC_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null)}"
  test -f "$A2MC_ROOT/a2mc_noncime_config.sh" || { echo "not in an A2MC clone — cd into it first"; exit 1; }
  ```
- **Never fabricate data.** Do not invent observation values, uncertainties, parameter bounds, or file paths the user did not give you. If a value is missing, ASK, or write a clearly-marked `TODO` placeholder and tell the user it must be filled before Phase 0. Fabricated targets silently corrupt the whole calibration.
- **Verify, don't assume.** Confirm the checkout's FATES/ELM commits and milestone with the tools below before telling the user which RAG profile applies. Never infer a parameter or mode's meaning from its name — check the RAG / knowledge base.
- **Confirm before writing.** Show the user the machine-config lines you will change, and any remote you will change on their model checkout (Step 2b), and get a yes first. A remote change on a checkout outside this repo is outward-facing.

## Step 0 — Greet + name the user, gauge experience, then orient (adapt the depth to them)

**Open with this greeting, word for word, the first time a user meets the agent in this clone** (PI, 2026-09-23). It is a fixed script, not a template to adapt: the setup tutorial shows new users this sentence as the first thing the agent says. Say it exactly, as plain text, with nothing before it in the reply; anything the start-up snapshot asked you to relay comes after it, in one short line. Then wait for the answer.

> Hi! I'm your A2MC agent, and I'll work with you as your science assistant to calibrate your model. What's your name, and how should I address you?

**It is said once per clone, never again** (PI: "this should only work the first time the new user interact with the agent"). Skip it when it has been said already, which is when `.greeted` exists at the clone root or you were handed it earlier in this conversation, and skip it when `.me` already names the user. If you skip it while `.me` is still missing, ask for the name in your own words. If you say it yourself because nothing handed it to you, record that it was said: `touch "$A2MC_ROOT/.greeted"`.

In Claude Code a `UserPromptSubmit` hook, `.claude/hooks/greet-on-setup.py`, hands you this sentence with the first request to set up A2MC in a clone that has not recorded its user in `.me`, and creates `.greeted` as it does, so the greeting is said before this skill has loaded and never after. The hook, this step, the interview questionnaire (Q0.0) and the tutorial (step 6) each carry a copy, and `tests/test_greet_on_setup.py` fails when any copy differs from the hook's: reword all four together.

Record the answer with **`python3 tools/whoami.py --set "<name>"`**, which writes the per-clone, gitignored `.me`.
**Do NOT write the name into a machine config**: both are tracked and on both sync legs' INCLUDE
lists, so a literal name there travels downstream and stamps other people's logs. The configs
resolve `A2MC_USER_NAME` from `whoami.py` instead of carrying a name. Beyond personalizing the session, it
sets the **Author field** for every log the user's work produces — `{A2MC_USER_NAME} with {coding-agent
name}` (e.g. *"Jing Tao with Claude Code"*); see the `calibration-log` skill. If the user declines,
record the neutral name instead, `python3 tools/whoami.py --set "A2MC user"`, so the author row resolves and
logs read `A2MC user with {coding-agent name}`; do not leave it unset, which fails the clone check for ever.

**Then gauge how familiar the user is with THE MODEL THEY ARE CALIBRATING** — whichever it is
(ELM / ELM-FATES, EcoSIM, PFLOTRAN, ATS, or one onboarded later) — by asking directly, or inferring
from how they answer Step 1. This sets how much you explain vs defer **for the whole session**:

- **New to the model** → be a teacher: orient them (the points below) and explain the relevant
  mechanism as each decision comes up. The examples throughout this skill are ELM-FATES because it is
  the worked reference case; **substitute the equivalent concept for another model — read it from that
  model's `ModelSpec.grouping_axis`, do not guess.** Declared today: `pft` for **FATES and EcoSIM**
  (EcoSIM has PFTs too), `region` for **PFLOTRAN and ATS**. Offer sensible defaults *with* the reasoning.
- **New to the model AND it is not yet onboarded** → they need `onboard-model`, which now includes an
  **orientation run** (Step 0d): A2MC builds the model with them and runs its own sample case, so
  neither of you is reasoning about a model nobody here has executed. Finish Step 1 first, then route
  there; `onboard-model` hands off to `onboard-case`, so this user does not come back here.
- **Experienced** → rely on their decisions: confirm their intent, don't lecture, and **do not impose a
  default over an explicit choice**. Skip the orientation they don't need and go straight to capturing
  their configuration.
- **Mixed / unsure** → orient lightly and check in as you go.

**Orientation for a user new to the modeling system — convey these plainly (skip/abbreviate for an expert).**
Points 1, 3 and 5 hold for **every** model; 2 and 4 are stated in ELM-FATES terms as the worked
example, and have a direct analogue in any adapter model (its own milestone/profile, its own
grouping axis) — say the analogue, not the FATES word, when the user is on another model:

1. **Two-layer configuration.** The *machine* config comes in two variants, one per model family: `a2mc_config.sh` for a CIME model (ELM / ELM-FATES: HPC allocation, E3SM root, output root, model checkout `A2MC_MODEL_PATH`, Python env, AI provider) and `a2mc_noncime_config.sh` for a standalone model (EcoSIM, PFLOTRAN, ATS: machine name, default MPI layout, Python env, AI provider, and deliberately **no** `A2MC_MODEL_PATH` or HPC account, which the site config sets). Use the one for the user's model, never both. `use_cases/{Model}_{Case}/config/<site>_config.sh` holds *site* settings **and overrides** the machine defaults for this site (spin-up protocol, PFTs, ensemble name, parameter/target files). Since v2.306 **the site config auto-sources the machine config** it needs (`a2mc_config.sh` for CIME/ELM-FATES, `a2mc_noncime_config.sh` for the adapter models) when one is not already loaded, so `source <site>_config.sh` alone is enough and the explicit `source a2mc_config.sh` first is a no-op. Either way the machine config loads **first** and the site config wins on any overlap, so nothing site-specific belongs in `a2mc_config.sh`.

> **If an AGENT is running this, join the `source` to the command that needs it** — `source … && <command>`. A harness gives each shell call a fresh process, so a config sourced on its own is gone by the next call, and the script then reports its variables unset as though nothing had been sourced. A human at a terminal is unaffected. Full statement: `AGENTS.md` §"Source the config and run in the SAME command".

2. **A2MC is mode-aware.** What it retrieves and how it runs depend on the *configuration* — ELM with or without FATES, carbon-only vs nutrient-enabled (CNP), ECA vs RD, and the FATES **milestone** matched from the checkout's commits (Step 2). Resolve this early so the right knowledge profile loads.
3. **The goal sets *what you calibrate*, not by itself the *run protocol*.** Your science question + data set the **target granularity** — ecosystem-level fluxes/states (tower/MODIS GPP, ET, NEE) vs per-PFT quantities (per-PFT biomass, phenology). That decides whether you must enumerate PFTs (`onboard-case` step 1.2). It does **not** decide spin-up: **spin-up is a separate decision** (`onboard-case` step 1B) — even a GPP-only run often needs spin-up to equilibrate carbon/soil pools. Ask; never infer "no spin-up" from an ecosystem goal.
4. **Grouping axis — for ELM-FATES, PFTs, and ELM vs FATES are different systems.** ELM's surface-dataset PFTs are **static** (prescribed fractional cover, fixed in time); FATES's PFTs are **dynamic** (they compete and evolve demographically). They have separate id mappings — a calibration target's PFT id refers to the **FATES** PFT list (read from the base parameter file, Step 2), *not* the ELM surfdata PFTs. Confirm which system the user means when they say "PFT."
5. **The 7-phase loop.** Setup (this skill) → Phase 0 design/submit → 1 explore → 2 screen → 3 diagnose → 4 hypothesize → 5 test → 6 refine → 7 converge. This skill covers only the per-clone part; `onboard-case` carries it to Phase 0.

**Before leaving Step 0 — confirm which model, and whether A2MC already has it.** `a2mc-init` sets a *clone* up for a model A2MC already supports; it does **not** teach A2MC a new model. A2MC supports ELM / ELM-FATES plus any model already onboarded in *this* repo — i.e. one with a registered `rag/milestones.json` profile and a `models/<name>/` adapter (run `python scripts/rag_list.py` to see them). Ask the user which model they are calibrating:
- **ELM / ELM-FATES, or a model already onboarded here** → continue through Steps 1–4; the model is built if needed and checked in Step 2, and the case itself is built by `onboard-case` (Step 4). **A CIME user should hear that `A2MC-elm` is the line developed for CIME models** (it ships the worked ELM-FATES case); continuing here is supported, since this line carries the ELM-FATES code path too. **On a workstation with no scheduler**, only EcoSIM can run today (`A2MC_EXEC_MODE=local`); a PFLOTRAN or ATS user there can still do everything up to Phase 0 (clone, case, plan, parameter list), and needs a machine with a scheduler for the ensemble itself.
- **A brand-new model not yet onboarded** (a different land/ecosystem model — CLM/CTSM, TEM, ReSOM, … — with no `rag/milestones.json` entry + `models/<name>/` adapter) → **do Step 1 (wire the clone) and Step 3 (the machine config for the model's family: CIME or standalone), then STOP and invoke the `onboard-model` skill.** Neither step depends on the adapter, and skipping Step 1 means the whole onboarding is committed with the repo's git hooks switched off. `onboard-model` builds the model's adapter + source-grounded knowledge chain (wiki → RAG → curated seed → milestone) so A2MC can reason about it, and builds the model itself with the user in its Step 0d, recording the recipe in `models/<m>/BUILD.md`. Once the model is onboarded, `onboard-model` hands off to `onboard-case`, whose Step 2 binds the case to the build; `a2mc-init` is finished for this user. Do **not** run the FATES/ELM-specific Step 2 tooling on a non-ELM checkout.

## Step 1 — Wire the clone, and learn who you are working with

**Do this FIRST, before the checkout and the config, and for EVERY user** — including one Step 0
routes to `onboard-model`. That user leaves this skill after this step and Step 3, so it is the only
chance this skill gets. `check_clone_setup.py` has five rows; four of them live outside the repository
tree or in the per-clone git index, so git cannot carry them and every fresh clone starts without
them. None is a matter of taste: without `core.hooksPath` the repo's own commit checks never fire
and a malformed message is accepted rather than refused; without the `skip-worktree` flag a
database file rewritten on every RAG read shows as permanently modified and gets swept into an
unrelated commit; without the memory symlink the agent's memories go to a personal directory and
reach nobody; without an author name A2MC stamps the wrong person onto every log it writes. The
fifth applies on NERSC only: a temp directory inside `$HOME`, since NERSC forbids writes outside it;
elsewhere it reports N/A. Its fix is one line in the shell profile, which reaches only a **new** shell: the
running agent session keeps its old environment until it is restarted, so say so rather than re-running
the checker in a loop. `setup_clone.sh` fixes the first three; the name is `whoami.py`, and the
temp directory is one line in your shell profile, which the checker prints.

**Which Python.** The setup checkers (`check_clone_setup.py`, `check_stage_ready.py`, `whoami.py`) run
under any `python3`, including Perlmutter's system 3.6. Everything else (`model_preflight.py`,
`create_use_case.py`, `rag_match.py`, the samplers) needs the A2MC environment: activate
`~/a2mc_env` first, and create it if it does not exist (`python3 -m venv ~/a2mc_env`, then
`~/a2mc_env/bin/pip install -r requirements.txt` from the repo root, with Python 3.10 or 3.11).

```bash
scripts/setup_clone.sh --dry-run     # preview
scripts/setup_clone.sh               # idempotent; safe to re-run
python3 tools/check_clone_setup.py   # exit 0 = wired. Setup is NOT done until this passes
```

**Do not ask for the name again: Step 0 captured it.** Confirm it resolves, and only if it does
not (`.me` was never written) go back to Step 0's question; a user who declined has the neutral name recorded there, so this check passes for them too. The name
is asked, never inferred ([[feedback_verify_or_ask_hard_stops]]):

```bash
python3 tools/whoami.py --verbose    # the name and where it came from; exit 1 = unresolved
```

`tools/whoami.py` resolves `$A2MC_USER_NAME` → `.me` → `git config user.name`, and **fails rather
than defaulting** when none resolves. It also flags a name taken from git as a GUESS, because that
field is usually a handle. This matters more than it looks: a case folder is often DELIVERED,
emailed and unpacked under `use_cases/`, and it arrives full of logs authored by whoever ran the
previous round, so an agent inferring the convention from neighbouring files has a plausible wrong
answer sitting in the same directory. `.me` is gitignored and per-clone on purpose; the machine
configs are TRACKED, so a name written into one travels to everyone who takes that clone.

**Then ask about GitHub, and take no for an answer.** A2MC needs no remote: git is fully
functional offline, and a user can run every phase, keep full history and never create an account.
A remote is recommended rather than required, so route on what they say:

| they say | do |
|---|---|
| they have an account | record the handle; it is what makes the fork-safe remotes in Step 2b possible |
| no account, happy local | confirm that nothing in A2MC requires one, and move on without pressing |
| no account, wary of publishing work | suggest a **PRIVATE** repository: full history and off-machine backup with nothing visible to anyone else. A2MC itself is developed this way, in a private repo with a filtered one-way publish, so the pattern is the project's own |

**This step is easy to skip and nothing downstream will mention it.** `tools/check_stage_ready.py`
reports stage 4, "setup is done", as soon as any case carries offline workflow state, and a
delivered case supplies that on the first session. The clone's wiring and the case's maturity are
independent facts; the per-clone rows now run at every stage for exactly that reason.

## Step 2 — Get, build and verify the model on this machine

For a model A2MC already has. (A model it does not have left after Step 3 for `onboard-model`, which
asks these same locations in its own Step 0a and builds the model with the user in its Step 0d.) This step is per machine: `onboard-case` Step 2
then binds each case to the install, and re-checks it, since a case may name another checkout.

### 2.1 — Is there a built model here? If not, get and build it

Ask where the model's source checkout is and, for a standalone model, where the built binary is. If
there is none, **ask where to put it** before building: the source checkout (it becomes `A2MC_MODEL_PATH`) and the archive root for built binaries both belong in a project or software space, never a node-local temp directory or a home directory close to its quota. Then build it now, with the user, from the model's build guide. That guide is the one place
the recipe lives, and it says honestly when a recipe is unverified or blocked:

| model | build guide | notes |
|---|---|---|
| EcoSIM | `models/ecosim/BUILD.md` | GCC 13 or older; the build script exits 0 on failure, so the binary's existence is the test |
| PFLOTRAN | `models/pflotran/BUILD.md` | rebuilt on Perlmutter 2026-09-23 on `cpe/25.09` (PETSc 3.21.4 built for it), after the Cray PE of the first build was removed; the guide says what to do when that recurs |
| ATS | `models/ats/BUILD.md` | built inside Amanzi; the ATS adapter itself is not finished onboarding (no milestone) |
| ELM / ELM-FATES | E3SM with its FATES submodule; the CIME line `A2MC-elm` is where this is developed and documented | clone `https://github.com/E3SM-Project/E3SM.git`, check out the commit the milestone names, and initialise the submodules; CIME builds per case |

A build usually outlasts one tool call (EcoSIM's takes about 30 minutes), so run it in the background
and watch its log, or hand the user the command for their own terminal; then test the binary exists.
A standalone model's binary must then be **archived** before any case binds to it (the build guides
show `tools/model_archive_build.sh`): a queued job resolves its executable at run time, and the next
build overwrites the shared tree in place ([[feedback_bind_runs_to_archived_binaries]]).

### 2.2 — Verify the checkout against A2MC's knowledge profiles

```bash
# ELM / ELM-FATES
python scripts/rag_list.py                                    # registered milestones
python scripts/rag_match.py --model-path "<E3SM checkout root>"
# EcoSIM, PFLOTRAN, ATS
python tools/model_preflight.py --model <name> --checkout "<model checkout root>" --param-file <param file>
```

Report the detected commit and the verdict to the user. `rag_match.py` is **ELM/FATES-only**: on any
other checkout it cannot find E3SM commits, which says nothing about the model, so never run it there.

| verdict (`model_preflight` exit) | meaning | route |
|---|---|---|
| match (0) | the checkout is the commit a registered profile describes | continue |
| **DRIFT** (3) | the model is onboarded; this commit is not the registered one | **continue, and say so.** A2MC reasons with the registered profile. Rebuild it (`rebuild-rag`; EcoSIM also has `ecosim-version-drift`) only if the user's source differs in the mechanisms being calibrated |
| NO MILESTONE (2) | the adapter registers but its onboarding stopped before its milestone (ATS today) | `onboard-model`, resuming at `check_stage_ready.py --model <m>`'s first failing row |
| CANNOT VERIFY (1) | no version could be read | fix the path, or go back to 2.1. A model installed without git metadata (tarball, conda, spack) can never be read: record its version by hand and treat it as drift |

For ELM-FATES, drift is a checkout at a commit no milestone names; `docs/a2mc_reference/version_association_workflow.md`
§"Drift handling" gives the T1/T2/T3 rebuild tiers. `api-43-1` is the canonical ELM-FATES profile and
`api-31-0` the frozen manuscript one.

The FATES **PFT inventory** is read per case, from the base parameter file the case will run:
`onboard-case` Step 2.

## Step 2b — Offer fork-safe remotes on the model checkout (guard against pushing to upstream)

A freshly-cloned model checkout has `origin` pointing at the **upstream** repo with **push enabled**, so a
stray `git push origin …` targets upstream. This holds for every model, not only ELM. **Check it, and offer
to make it fork-safe** (especially if the user plans model-*development*, editing the model's source; pure
calibration users never push to the model repo, but the guard is harmless and worth offering). Which
repositories to check depends on the model:

| model | repos to check |
|---|---|
| ELM / ELM-FATES | the E3SM root **and** the FATES submodule (`E3SM-Project/E3SM`, `NGEET/fates` upstream) |
| EcoSIM, PFLOTRAN, ATS | the one checkout at `$A2MC_MODEL_PATH`. PFLOTRAN's source lives on Bitbucket, not GitHub; its runbook `pflotran-run-workflow` has the repository details |

Do not assert an upstream URL from memory: read it off `remote -v`.

```bash
git -C "$A2MC_MODEL_PATH" remote -v
# ELM-FATES only: the FATES submodule is a second repository with its own origin
git -C "$A2MC_MODEL_PATH/components/elm/src/external_models/fates" remote -v
```

If `origin` is an upstream URL with push enabled, **ask the user** whether they will edit the model's
source, and whether they have their own fork of each repo. Then, for each repo from the table, with the
repo's path written out in the command (a shell variable set in an earlier call is gone by the next one,
and `git -C ""` silently acts on the A2MC clone itself):

| the user | do |
|---|---|
| has a fork | add it as `fork`, disable `origin` push, and verify **both** directions (the procedure is `onboard-model` Step 0b, which also covers a non-GitHub upstream such as PFLOTRAN's Bitbucket) |
| has no fork or no GitHub account | offer only the sentinel: `git -C <repo path> remote set-url --push origin DISABLED_push_to_fork_not_upstream`. A calibration-only user never pushes model source, so this is defence in depth, not a requirement |
| declines | record nothing and move on; `check_stage_ready.py` reports the guard as advisory, never as a failure |

```bash
git -C <repo path> remote add fork "<the user's fork URL>"       # SSH if the token lacks `workflow` scope
git -C <repo path> remote set-url --push origin DISABLED_push_to_fork_not_upstream
git -C <repo path> push origin HEAD --dry-run                    # must FAIL
git -C <repo path> push fork   HEAD --dry-run                    # must SUCCEED
```

This is **per-clone git config (not committed)**: re-apply on any re-clone. Changing remotes on a checkout
outside this repo is outward-facing, so get a yes first. Model development then happens on experiment
branches off the pinned anchor, default-off and V0-at-equality: the `model-evolution` skill (any model;
`add-fates-parameter` is its FATES sub-recipe) and the memory [[feedback_model_source_push_fork_only]].

## Step 3 — Set up machine config (if needed)

Every user, once per clone; a user onboarding a new model does it before `onboard-model`.

**Pick the machine config by how the model is built and run, and edit only that one.** The two are
parallel files, not layers: a non-CIME model must not inherit `a2mc_config.sh`, whose E3SM-rooted
`A2MC_MODEL_PATH` default would shadow the model's own checkout ([[feedback_two_machine_configs_cime_vs_noncime]]).

| model | machine config | where the model checkout, binary, HPC account and output root are set |
|---|---|---|
| ELM / ELM-FATES (CIME) | `a2mc_config.sh` | here, in the machine config |
| EcoSIM, PFLOTRAN, ATS (non-CIME) | `a2mc_noncime_config.sh` | the **site** config, which `onboard-case` writes from `use_cases/{Model}_template/` |

In both files the author name is NOT set: `python3 tools/whoami.py --set "<name>"` (Step 0) writes the
per-clone `.me`, and each config resolves `A2MC_USER_NAME` from it. Both files are tracked and SHIP on
both sync legs, so a literal name would stamp every downstream user's logs.

**(a) CIME model** — if `a2mc_config.sh` is not yet customized, walk the user through the minimal set:

```bash
# In a2mc_config.sh:
export A2MC_PROJECT="<HPC allocation>"
export A2MC_E3SM_ROOT="<E3SM source>"
export A2MC_OUTPUT_ROOT="<simulation output root>"
export A2MC_MODEL_PATH="<E3SM/ELM-FATES checkout root>"   # REQUIRED
export A2MC_SCRIPTS_DIR="<where CIME case scripts go>"    # ships with the developer's own path
export A2MC_EMAIL="<your email>"                          # scheduler notifications; ships with a default
export A2MC_AI_PROVIDER="anthropic"                       # or openai / cborg
```

**Check every value the file ships with, not only these**: it carries the developer's own paths and
project, and a path written in quotes as `"~/..."` is never expanded by the shell.

**(b) Non-CIME model** — `a2mc_noncime_config.sh` carries only the settings every model shares, and most
users change little in it. Walk through these, and leave the rest at their defaults:

```bash
# In a2mc_noncime_config.sh:
export A2MC_MACHINE="${A2MC_MACHINE:-pm-cpu}"         # the machine name; a site config may override
export A2MC_VENV="${HOME}/a2mc_env"                   # the Python env this file activates
export A2MC_AI_PROVIDER="${A2MC_AI_PROVIDER:-cborg}"  # or anthropic / openai
# MPI layout per ensemble member, SERIAL by default. Leave it here: a site config that needs
# ranks sets its own value UNCONDITIONALLY (a bare export), because a `${VAR:-N}` fallback in
# the site config is inert once this file has set the variable.
export A2MC_HPC_MPI_RANKS="${A2MC_HPC_MPI_RANKS:-1}"
```

This file deliberately sets **no** `A2MC_MODEL_PATH`, binary path, HPC account or output root. Do not
add them here: they belong to the case, so `onboard-case` fills them in the site config (for example
`A2MC_MODEL_PATH`, `A2MC_ECOSIM_BINARY` / `A2MC_PFLOTRAN_BINARY` / `A2MC_ATS_EXE`, `A2MC_HPC_ACCOUNT`).
Record the checkout path verified in Step 2 so `onboard-case` can use it. A workstation run with no
scheduler is `export A2MC_EXEC_MODE=local` (default `hpc`; read by the EcoSIM backend today, in
`models/ecosim/backend.py`), exported in the site config or the shell; monitor it with
`arm-local-monitoring` rather than `arm-hpc-monitoring`.

API key (online agent only): `echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc && source ~/.bashrc`. Full field reference: `docs/a2mc_reference/user_guide.md` §2. Do not paste real keys into tracked files.

## Step 4 — Route onward (the case arc lives in `onboard-case`)

The clone is now set up: wired, the model built and verified on this machine, the machine config
written. **Everything from here is per-case, not per-clone**, so it belongs to a skill that can run
again for the second case and the tenth. Re-run the router and follow its `NEXT:` line:

```bash
python3 tools/check_stage_ready.py
```

| the user wants | invoke |
|---|---|
| a calibration case on a model A2MC already has (ELM-FATES, or `check_stage_ready.py --model <m>` shows no ✗) | **`onboard-case`** |
| a model A2MC has never seen | **`onboard-model`** first, then `onboard-case` |
| to resume a case that already exists | **`onboard-session`** |

`onboard-case` runs the science-goal interview, drafts the research plan (GATE 1), scaffolds
`use_cases/{Model}_{Case}/` from **that model's** template, builds or vets the parameter list (GATE 2),
runs `check_setup_ready.py`, and hands off to `phase0-design`.

**Tell the user which runbook skill serves their model** — it is what they and the agent will lean on
for every run once the case exists, and naming it now saves them finding it by accident:

| model | runbook skill |
|---|---|
| ELM / ELM-FATES | `offline-testing-workflow` (reached through `phase5-testing`) |
| EcoSIM | `ecosim-run-workflow` |
| PFLOTRAN | `pflotran-run-workflow` |
| ATS | `ats-run-workflow` |

**Do not do any of that here.** Those steps lived in this skill until 2026-08-02 and were unreachable
for a second case, because this skill announces itself as first-run-only. Duplicating them back would
recreate the drift that split them out.

## Footguns

- **A2MC_MODEL_PATH unset** — the orchestrator hard-fails at startup. Verify the checkout in Step 2; for a CIME model set it in `a2mc_config.sh` (Step 3a), for a non-CIME model `onboard-case` Step 2 binds it and Step 4 writes it into the site config.
- **Treating drift as "unsupported"** — `model_preflight` exit 3 means the model IS onboarded and the checkout is at another commit: proceed and say so. Only exit 2 (no milestone) goes to `onboard-model`. Until 2026-09-23 both were exit 2 and every user off the one registered commit was sent to re-onboard an onboarded model.
- **Handing a user a binary on the live build path** — a queued job resolves its executable at run time, and the next build overwrites it. Archive first (Step 2.1).
- **Routing to `onboard-model` before Step 1** — that user never comes back to this skill, so the clone stays unwired: `core.hooksPath` unset means `.githooks/pre-commit` and `commit-msg` never run, and the whole model onboarding is committed unchecked. `.claude/hooks/` are not affected (they load from the tracked `.claude/settings.json`), which is why the SessionStart warning still appears and the git hooks still stay off.
- **Editing the wrong machine config** — a non-CIME model uses `a2mc_noncime_config.sh`, never `a2mc_config.sh`, whose E3SM-rooted `A2MC_MODEL_PATH` default shadows the model's checkout. Every shipped site config auto-loads the right one and repairs the wrong one if it was sourced, so the harm is in *editing* the wrong file: the settings never reach the run.
- **ELM tooling on a non-CIME checkout** — `rag_match.py`, the `fates_utils` PFT read and the FATES-submodule remote check are ELM-only; a non-CIME model uses `tools/model_preflight.py` (Step 2) and a single checkout (Step 2b).
- **Doing the case work here** — the interview, `research_plan.md`, `use_cases/…`, `targets.yaml`, the parameter list and `check_setup_ready.py` all belong to `onboard-case`. They lived here until 2026-08-02 and were unreachable for a second case. Route (Step 4); do not re-inline them.
- **Asserting a milestone without verifying** — always run `rag_match.py` (ELM) or `model_preflight.py` (others); never name the profile from the folder name or an assumption.
- **Treating an unsupported model as drift** — a non-ELM/FATES checkout (no matching `rag/milestones.json` entry + `models/<name>/` adapter) is NOT a drift case; it needs the `onboard-model` skill (build the adapter + knowledge chain), which hands off to `onboard-case`. Ask which model up front (Step 0) so you don't run FATES-specific tooling on a non-ELM checkout.
- **Bare relative path from the wrong cwd** — always derive `A2MC_ROOT="$(git rev-parse --show-toplevel)"` and prefix writes. `A2MC_ROOT` is unset on a first run (a site config sets it, none exists yet), and an *empty* prefix writes at the filesystem root.
- **Naming a milestone without matching the checkout** — to associate the user's ELM + FATES commits with a registered RAG milestone, run `scripts/rag_match.py` (never assert the profile from a folder name). Auto-detection, drift tiers T1/T2/T3, and the five scripts are documented in `docs/a2mc_reference/version_association_howto.md`.

## Cross-references

- **`onboard-case`** — where this hands off for everything per-case (interview → plan → use case → param list → Phase 0). The steps it owns were extracted from here on 2026-08-02.
- `onboard-model` — for a model with no `models/<model>/` adapter; run it before `onboard-case`.
- `onboard-session` — the resume-an-existing-setup counterpart (route there once a case exists).
- Per-model runbooks (Step 4): `ecosim-run-workflow`, `pflotran-run-workflow`, `ats-run-workflow`, and `offline-testing-workflow` for ELM-FATES; `arm-local-monitoring` for a workstation run with no scheduler.
- `docs/a2mc_reference/user_guide.md` §1–§3 (install/config/run), §6 (knowledge system); `rag_reference.md` (RAG query how-to + Python-3.10 binary).
- `docs/a2mc_reference/version_association_howto.md` — **match ELM + FATES commits to a registered RAG milestone** (the Step-2 milestone step: `rag_match.py`, drift tiers, the five scripts); `version_association_workflow.md`, `mode_aware_workflow.md` — deeper milestone + mode detail.

