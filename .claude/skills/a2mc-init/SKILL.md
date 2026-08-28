---
name: a2mc-init
visibility: public
category: meta
description: First-run interactive setup for the offline agent — the per-CLONE half of getting started, run once when A2MC is first used on a machine or in a fresh clone. Greet and gauge the user's experience, verify the model checkout against the RAG milestone registry, offer fork-safe remotes on that checkout, and write the machine config (a2mc_config.sh for a CIME model, a2mc_noncime_config.sh for a standalone one), then ROUTE onward — to onboard-model for a model A2MC has never seen, or to onboard-case to create the calibration case itself. Use when the user says "set up A2MC", "first time using A2MC", "help me get started / onboard me to A2MC", "configure A2MC on this machine". DISTINCT from onboard-session (which resumes an ALREADY-configured setup) and from onboard-case (which creates a case and is repeatable).
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [setup]
  summary: "Per-clone first-run setup: greet -> verify checkout + RAG milestone -> fork-safe remotes -> machine config -> route to onboard-model / onboard-case."
---

<!-- ───────────────────────── At a glance ───────────────────────── -->
```text
Step 0  greet + gauge experience + orient ──► if a NEW (un-onboarded) model → STOP, run onboard-model FIRST
Step 1  interview (goal → granularity → PFTs/targets/params)
Step 2  verify checkout + milestone + PFT inventory
Step 3  machine config
Step 4  draft research_plan.md ──► ★ GATE 1 (iterate until approved): plan ◄──
          then: record memory + write site config + targets.yaml
Step 4b parameter list + ensemble design (scheme/size/cost — show trade-offs)
          ──► ★ GATE 2 (iterate until agreed) ◄── then: round record
Step 5  check_setup_ready.py  (goal-conditional; all ✗ resolved)
Step 6  hand off to phase0-design
```

# a2mc-init — first-run setup (offline agent)

The **front door** for a new A2MC user. The offline agent (a coding-agent harness opened in the repo) runs this once to turn "I cloned A2MC" into "I have a configured, mode-resolved use case ready for Phase 0." It interviews the user, verifies their model checkout against the RAG milestone registry, writes the site config + validation targets, and hands off to `phase0-design`.

**This is not `onboard-session`.** `onboard-session` is the cold-start runbook for an **already-configured** setup (read the handoff, catch up, resume in-flight work). `a2mc-init` is for the **first run**, when there is no site config yet. Decision:

```
Is there a customized a2mc_config.sh AND a use_cases/{Model}_{Case}/ for this work?
  ├── No  → a2mc-init (this skill): set it up from scratch.
  └── Yes → onboard-session: resume the existing setup.
```

If the user is midway (config exists, site half-built), do the missing steps here, then route to `onboard-session`.

## Core discipline (read first)

> **Definition of done for this stage: `setup-discipline`.** This skill performs the stage; that one
> collects what "finished" means for it, with the executable gate per item. Check it before
> declaring this stage complete.


This skill writes files and asserts model behavior, so the offline-agent operating discipline applies hard
— the four failure modes + the gate enforcing each are in `AGENTS.md` §"Offline-Agent Operating Discipline"
(lead memory `feedback_offline_agent_operating_discipline`). In this skill that means especially:

- **Anchor every write to the A2MC repo root — never a bare relative path.** This skill's paths
  (`use_cases/…`, `a2mc_config.sh`, `tools/…`, `scripts/…`) are relative to the **repo root**; if the agent's
  cwd is elsewhere, a bare `use_cases/$CASE_DIR` write lands in the wrong place. **`CASE_DIR` holds the canonical case-folder name, `{Model}_{Case}`** (`EcoSIM_BioCON`, `PFLOTRAN_miniLEO`), the rule `onboard-case` owns; it was `$SITE` until 2026-08-24, which invited a site name with no model component. `A2MC_ROOT` is **not** set on a
  first run (a site config sets it, and none exists yet) — so **derive it** and prefix all writes with it:
  ```bash
  A2MC_ROOT="${A2MC_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null)}"
  test -f "$A2MC_ROOT/a2mc_config.sh" || { echo "not in an A2MC clone — cd into it first"; exit 1; }
  ```
  Then write under `"$A2MC_ROOT/use_cases/$CASE_DIR/…"`. **Never** `$A2MC_ROOT/…` while `A2MC_ROOT` is unset — an
  empty prefix expands to `/use_cases/$CASE_DIR`, i.e. the filesystem root.
- **Never fabricate data.** Do not invent observation values, uncertainties, parameter bounds, or file paths the user did not give you. If a value is missing, ASK, or write a clearly-marked `TODO` placeholder and tell the user it must be filled before Phase 0. Fabricated targets silently corrupt the whole calibration.
- **Verify, don't assume.** Confirm the checkout's FATES/ELM commits and milestone with the tools below before telling the user which RAG profile applies. Never infer a parameter or mode's meaning from its name — check the RAG / knowledge base.
- **Confirm before writing.** Show the user what you will create (paths + key values) and get a yes before creating the use case dir and files. Creating a use case is reversible, but overwriting an existing one is not — never clobber an existing `use_cases/{Model}_{Case}/`.
- **Env vars = intent.** The site config's mode env vars represent what the user *intends* to calibrate (v2.94+); they are the source of truth, later enriched (not overridden) by the CIME case dir. See `feedback_env_vars_are_intent_case_dir_is_truth`.

## Step 0 — Greet + name the user, gauge experience, then orient (adapt the depth to them)

**Open with a greeting and capture the user's name:** *"Hi! I'm your A2MC agent — I'll work with you as
your science assistant to calibrate your model. What's your name, and how should I address you?"* Record
it as **`A2MC_USER_NAME`** (written to `a2mc_config.sh` in Step 3). Beyond personalizing the session, it
sets the **Author field** for every log the user's work produces — `{A2MC_USER_NAME} with {coding-agent
name}` (e.g. *"Jing Tao with Claude Code"*); see the `calibration-log` skill. If the user declines,
fall back to `A2MC user with {coding-agent name}`.

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
  neither of you is reasoning about a model nobody here has executed. Route there first; come back.
- **Experienced** → rely on their decisions: confirm their intent, don't lecture, and **do not impose a
  default over an explicit choice**. Skip the orientation they don't need and go straight to capturing
  their configuration.
- **Mixed / unsure** → orient lightly and check in as you go.

**Orientation for a user new to the modeling system — convey these plainly (skip/abbreviate for an expert).**
Points 1, 3 and 5 hold for **every** model; 2 and 4 are stated in ELM-FATES terms as the worked
example, and have a direct analogue in any adapter model (its own milestone/profile, its own
grouping axis) — say the analogue, not the FATES word, when the user is on another model:

1. **Two-layer configuration.** `a2mc_config.sh` holds *machine* settings (HPC allocation, output root, model checkout `A2MC_MODEL_PATH`, Python env, AI provider). `use_cases/{Model}_{Case}/config/<site>_config.sh` holds *site* settings **and overrides** the machine defaults for this site (spin-up protocol, PFTs, ensemble name, parameter/target files). Since v2.306 **the site config auto-sources the machine config** it needs (`a2mc_config.sh` for CIME/ELM-FATES, `a2mc_noncime_config.sh` for the adapter models) when one is not already loaded, so `source <site>_config.sh` alone is enough and the explicit `source a2mc_config.sh` first is a no-op. Either way the machine config loads **first** and the site config wins on any overlap, so nothing site-specific belongs in `a2mc_config.sh`.
2. **A2MC is mode-aware.** What it retrieves and how it runs depend on the *configuration* — ELM with or without FATES, carbon-only vs nutrient-enabled (CNP), ECA vs RD, and the FATES **milestone** matched from the checkout's commits (Step 2). Resolve this early so the right knowledge profile loads.
3. **The goal sets *what you calibrate*, not by itself the *run protocol*.** Your science question + data set the **target granularity** — ecosystem-level fluxes/states (tower/MODIS GPP, ET, NEE) vs per-PFT quantities (per-PFT biomass, phenology). That decides whether you must enumerate PFTs (`onboard-case` step 1.2). It does **not** decide spin-up: **spin-up is a separate decision** (`onboard-case` step 1B) — even a GPP-only run often needs spin-up to equilibrate carbon/soil pools. Ask; never infer "no spin-up" from an ecosystem goal.
4. **Grouping axis — for ELM-FATES, PFTs, and ELM vs FATES are different systems.** ELM's surface-dataset PFTs are **static** (prescribed fractional cover, fixed in time); FATES's PFTs are **dynamic** (they compete and evolve demographically). They have separate id mappings — a calibration target's PFT id refers to the **FATES** PFT list (read from the base parameter file, Step 2), *not* the ELM surfdata PFTs. Confirm which system the user means when they say "PFT."
5. **The 7-phase loop.** Setup (this skill) → Phase 0 design/submit → 1 explore → 2 screen → 3 diagnose → 4 hypothesize → 5 test → 6 refine → 7 converge. This skill covers only the per-clone part; `onboard-case` carries it to Phase 0.

**Before anything else — confirm which model, and whether A2MC already has it (else route to `onboard-model` FIRST).** `a2mc-init` sets a *clone* up for a model A2MC already supports; it does **not** teach A2MC a new model. A2MC supports ELM / ELM-FATES plus any model already onboarded in *this* repo — i.e. one with a registered `rag/milestones.json` profile and a `models/<name>/` adapter (run `python scripts/rag_list.py` to see them). Ask the user which model they are calibrating:
- **ELM / ELM-FATES, or a model already onboarded here** → continue with this skill; the milestone is confirmed mechanically in Step 2, and the case itself is built by `onboard-case` (Step 4).
- **A brand-new model not yet onboarded** (a different land/ecosystem model — CLM/CTSM, ATS, TEM, ReSOM, … — with no `rag/milestones.json` entry + `models/<name>/` adapter) → **STOP and invoke the `onboard-model` skill first.** It builds the model's adapter + source-grounded knowledge chain (wiki → RAG → curated seed → milestone) so A2MC can reason about it. That is a prerequisite; once the model is onboarded, `onboard-model` hands off to `onboard-case` for the site. Do **not** run the FATES/ELM-specific Step 2 tooling on a non-ELM checkout.

## Step 2 — Verify the checkout and RAG milestone

Before writing config, confirm the model version so the right knowledge profile loads.

```bash
export A2MC_MODEL_PATH="<user's E3SM/ELM-FATES checkout root>"
python scripts/rag_list.py                                 # registered milestones (api-43-1, api-31-0)
python scripts/rag_match.py --model-path "$A2MC_MODEL_PATH" # detect FATES+ELM commits → matched milestone
```

Report the detected FATES + ELM commits and the matched milestone to the user. **Distinguish the two no-match cases — they route differently:**
- **(a) Drift** — a supported ELM/FATES checkout at a *different commit* than any registered milestone. Say so and point to `docs/a2mc_reference/version_association_workflow.md` "Drift handling" (T1/T2/T3 rebuild); do not silently proceed on a mismatched profile.
- **(b) Unsupported model** — `rag_match.py` finds no FATES/ELM commits at all (the checkout is a *different model*), or the user named a non-ELM model in Step 0. This is **NOT drift** — no rebuild helps, because the model itself isn't onboarded. **STOP and route to the `onboard-model` skill** (build the adapter + knowledge chain first), then return here for site setup.

`api-31-0` is the frozen Kougarok-manuscript milestone; `api-43-1` is canonical.

**For an onboarded NON-ELM model (e.g. EcoSIM), use the generic preflight instead of the
FATES tooling** — `rag_match.py` + `fates_utils` are ELM/FATES-specific. `tools/model_preflight.py`
dispatches version-detection + the PFT/subgrid inventory through the model's adapter (`ModelSpec`):
```bash
python tools/model_preflight.py --model <name> --checkout "$A2MC_MODEL_PATH" --param-file <model param file>
```
It prints the detected version, the matched milestone (or "UNMATCHED → onboard-model"), the
model's own grouping-axis count (e.g. EcoSIM `pft` = 3), and the calibratable parameter count.
Exit 2 = no milestone match (unsupported/drift → `onboard-model`). This is the model-generic
analog of the FATES Step-2 tooling above (roadmap L3.2).

**Also read the PFT inventory from the checkout's base parameter file** — the same gate that reads commits should read the PFTs, so the total count and id↔name mapping come from the model the user actually runs (NEVER hardcode a PFT count; FATES can change its PFT system):

```bash
python -c "from tools.fates_utils import get_pft_names_from_file as g; \
  d=g('$A2MC_MODEL_PATH/components/elm/src/external_models/fates/parameter_files/fates_params_default.json'); \
  print(f'{len(d)} PFTs total'); [print(f'  PFT#{i} = {n}') for i,n in d.items()]"
```

Report the **total PFT count** and the full `PFT#id = name` list to the user. This count is authoritative: A2MC reads it at runtime (`get_n_pft_from_file`) and the SZPF extraction derives its level total (= count × 13 size classes) from the file, so nothing assumes 12/14/etc. Use this exact list to (a) do the target→PFT-id mapping in Step 1.2 and (b) fill `A2MC_PFTS` in Step 3 with the **1-based FATES ids** of the calibrated PFTs. If the user's targets name a PFT not in this list, stop — the checkout and the target set disagree.

## Step 2b — Offer fork-safe remotes on the model checkout (guard against pushing to upstream)

A freshly-cloned E3SM/ELM-FATES checkout has `origin` pointing at the **upstream** repo (usually
`E3SM-Project/E3SM` for E3SM and `NGEET/fates` for the FATES submodule) with **push enabled** — so a stray
`git push origin …` targets upstream. **Check it, and offer to make it fork-safe** (especially if the user
plans model-*development* — editing ELM/FATES source; pure calibration users never push to the model repo,
but the guard is harmless and worth offering):

```bash
git -C "$A2MC_MODEL_PATH" remote -v
git -C "$A2MC_MODEL_PATH/components/elm/src/external_models/fates" remote -v   # FATES submodule
```

If `origin` is an upstream URL with push enabled, **ask the user**: (1) do they have their own fork of
E3SM and of FATES (give the fork URLs), and (2) may you set the remotes so pushes can only go to their fork?
If yes, for **each** repo (E3SM root + the FATES submodule) set it up for them:

```bash
git -C "$REPO" remote add fork "<user's fork URL for this repo>"     # e.g. git@github.com:<user>/E3SM.git
git -C "$REPO" remote set-url --push origin DISABLED_no_push_to_upstream   # `git push origin` now fails loudly
# thereafter: git push fork <branch>
```

Prefer **SSH** fork URLs — an HTTPS token without the `workflow` scope is refused when the history touches
`.github/workflows/`. This is **per-clone git config (not committed)** — re-apply on any re-clone. Model-dev
then happens on **experiment branches** off the pinned anchor, default-off + V0-at-equality; see the
`add-fates-parameter` skill and the memory [[feedback_model_source_push_fork_only]] for the full contract.
Record the user's fork URLs + intended experiment branch in their case memory if they opt in.

## Step 3 — Set up machine config (if needed)

If `a2mc_config.sh` is not yet customized, walk the user through the minimal set:

```bash
# In a2mc_config.sh:
export A2MC_USER_NAME="<how the user asked to be addressed>"  # from the Step-0 greeting; author field
export A2MC_PROJECT="<HPC allocation>"
export A2MC_E3SM_ROOT="<E3SM source>"
export A2MC_OUTPUT_ROOT="<simulation output root>"
export A2MC_MODEL_PATH="<E3SM/ELM-FATES checkout root>"   # REQUIRED
export A2MC_AI_PROVIDER="anthropic"                       # or openai / cborg
```

API key (online agent only): `echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc && source ~/.bashrc`. Full field reference: `docs/a2mc_reference/user_guide.md` §2. Do not paste real keys into tracked files.

## Step 4 — Route onward (the case arc lives in `onboard-case`)

The clone is now set up: machine config written, checkout verified, milestone matched, remotes made
fork-safe. **Everything from here is per-case, not per-clone**, so it belongs to a skill that can run
again for the second case and the tenth.

| the user wants | invoke |
|---|---|
| a calibration case on a model A2MC already has (`models/<model>/` exists) | **`onboard-case`** |
| a model A2MC has never seen | **`onboard-model`** first, then `onboard-case` |
| to resume a case that already exists | **`onboard-session`** |

`onboard-case` runs the science-goal interview, drafts the research plan (GATE 1), scaffolds
`use_cases/{Model}_{Case}/` from **that model's** template, builds or vets the parameter list (GATE 2),
runs `check_setup_ready.py`, and hands off to `phase0-design`.

**Do not do any of that here.** Those steps lived in this skill until 2026-08-02 and were unreachable
for a second case, because this skill announces itself as first-run-only. Duplicating them back would
recreate the drift that split them out.

## Footguns

- **A2MC_MODEL_PATH unset** — the orchestrator hard-fails at startup. Set it in Step 3, verify in Step 2.
- **Doing the case work here** — the interview, `research_plan.md`, `use_cases/…`, `targets.yaml`, the parameter list and `check_setup_ready.py` all belong to `onboard-case`. They lived here until 2026-08-02 and were unreachable for a second case. Route (Step 4); do not re-inline them.
- **Asserting a milestone without verifying** — always run `rag_match.py`; never name the profile from the folder name or an assumption.
- **Treating an unsupported model as drift** — a non-ELM/FATES checkout (no matching `rag/milestones.json` entry + `models/<name>/` adapter) is NOT a drift case; it needs the `onboard-model` skill FIRST (build the adapter + knowledge chain), then `a2mc-init` for the site. Ask which model up front (Step 0) so you don't run FATES-specific tooling on a non-ELM checkout.
- **Bare relative path from the wrong cwd** — always derive `A2MC_ROOT="$(git rev-parse --show-toplevel)"` and prefix writes (`"$A2MC_ROOT/use_cases/$CASE_DIR/…"`). `A2MC_ROOT` is unset on a first run (a site config sets it, none exists yet), so `$A2MC_ROOT/use_cases/$CASE_DIR` with an *empty* prefix expands to `/use_cases/$CASE_DIR` — the filesystem root. Verify `$A2MC_ROOT/a2mc_config.sh` exists before writing.
- **Naming a milestone without matching the checkout** — to associate the user's ELM + FATES commits with a registered RAG milestone, run `scripts/rag_match.py` (never assert the profile from a folder name). Auto-detection, drift tiers T1/T2/T3, and the five scripts are documented in `docs/a2mc_reference/version_association_howto.md`.

## Cross-references

- **`onboard-case`** — where this hands off for everything per-case (interview → plan → use case → param list → Phase 0). The steps it owns were extracted from here on 2026-08-02.
- `onboard-model` — for a model with no `models/<model>/` adapter; run it before `onboard-case`.
- `onboard-session` — the resume-an-existing-setup counterpart (route there once a case exists).
- `docs/a2mc_reference/user_guide.md` §1–§3 (install/config/run), §6 (knowledge system); `rag_reference.md` (RAG query how-to + Python-3.10 binary).
- `docs/a2mc_reference/version_association_howto.md` — **match ELM + FATES commits to a registered RAG milestone** (the Step-2 milestone step: `rag_match.py`, drift tiers, the five scripts); `version_association_workflow.md`, `mode_aware_workflow.md` — deeper milestone + mode detail.

## Changelog
- 2026-08-26: **The two-step source order is now optional, and this file says so.** v2.306 gave every shipped site config a guard that auto-sources its own machine config (`a2mc_config.sh` for CIME/ELM-FATES, `a2mc_noncime_config.sh` for the adapter models) when one is not already loaded, and REPAIRS the wrong one if it was sourced by mistake. Nothing here was wrong -- the explicit machine-then-site order still works and still takes precedence -- so the instruction is shortened and the old form kept as a stated no-op. Asserted by `tests/test_site_config_autosource.py`. PI-directed. Principle 1 said "You always `source a2mc_config.sh` **then** `source <site>_config.sh`"; the always is gone, the precedence it was protecting is restated.
- 2026-08-24: **The shell placeholder is `$CASE_DIR`, not `$SITE`, and it holds `{Model}_{Case}`.** PI-directed normalisation across the whole shipped surface: `use_cases/{site}`, `use_cases/<site>` and `use_cases/<Model>_<Case>` are gone, one canonical brace form remains. The old name is what the 2026-08-07 entry below flagged and did not fix: a variable called `SITE` invites `use_cases/ELM-FATES_Kougarok` over `use_cases/FATES_Kougarok`, which is exactly the drift the naming rule exists to stop. The entry below keeps `$SITE` because it is describing the old name.


- 2026-08-02: **Split — the case arc moved to `onboard-case`.** This skill was two things wearing one
  name: per-clone setup (greet, checkout, milestone, fork guard, machine config) and per-case setup
  (interview, research plan, use case, parameter list, preflight, Phase-0 hand-off). Because its
  description said *first* run, **a second case had no entry point** — and the naming rule drifted, with
  `use_cases/$SITE` (no model component) on 22 lines here against `use_cases/<name>_<site>/` in
  `onboard-model`. Steps 1, 4, 4b, 5 and 6 were **moved** (not copied) into `onboard-case`, which now
  owns case creation alone; Step 4 here is a routing table. Case-specific footguns moved with them.
  Audit: `20260802e`.
- 2026-07-11: **Step 0 (gauge experience + orient) + `calibration_rounds.yaml` in the flow + goal-conditional Step-5 gate.**
  Added **Step 0**: first **gauge the user's ELM/ELM-FATES experience** and adapt session-wide depth
  (teach + orient novices; defer to experts, don't impose defaults over an explicit choice), then orient
  (two-layer config where the site config *overrides* the machine config, mode-awareness, the 7-phase
  loop). Two model-fidelity corrections folded in (PI): **spin-up is a separate decision from target
  granularity** (even a GPP goal may need spin-up — interviewed in 1B, not inferred), and **ELM's static
  surfdata PFTs are distinct from FATES's dynamic PFTs** (a target's PFT id is a FATES id from the base
  file — noted in Step 0 + interview 1.2). Fixed a stale var name (`A2MC_PFT_LIST` → `A2MC_PFTS`). Step 4 (b) now generates the **round
  record** from the sourced config (`tools/generate_calibration_rounds.py --write` → fill TODO
  narrative → `check_calibration_rounds.py`) instead of hand-authoring it. **Step 5** replaced with
  `tools/check_setup_ready.py`, a single **goal-conditional** readiness gate (universal checks +
  `N/A` for PFT inventory on ecosystem goals, FATES/RAG when FATES off, spin-up reported-not-required;
  wraps `validate_targets_config.py` + `check_calibration_rounds.py`). New footguns (hand-authoring
  the round record; naming a milestone without `rag_match.py`; treating `N/A` as a blocker) + cross-ref
  to `version_association_howto.md`. Distilled from the api-31→api-43 Kougarok migration (dev_logs
  20260710o–y, 20260711a) — that migration IS the new-site/new-user prep path. Requested by the PI.
- 2026-07-09: **Step 2b — offer fork-safe model-checkout remotes.** After verifying the checkout, the agent
  now checks the model repo's git remotes (E3SM root + FATES submodule); if `origin` is an upstream URL with
  push enabled, it asks the user for their fork URLs and (with consent) adds a `fork` remote + disables push
  to `origin`, so a stray `git push origin` can't reach upstream. Generic (no host assumptions); prefers SSH
  (HTTPS PAT without `workflow` scope is refused on `.github/workflows/`). Pairs with the model-dev track
  (`add-fates-parameter`, `feedback_model_source_push_fork_only`). Requested by the PI.
- 2026-07-09: **Variant-aware targets.** Interview 1D + research plan + Step-4 `targets.yaml` now classify each
  target's variant — snapshot / time-series / several-snapshots (an `observations:` list, scored on all points)
  / several stocks (separate targets) — and match the per-target `cost_method` to it (skill scores like
  `nse`/`kge` need ≥2 points). Pairs with the `evaluate_case.py` time-series upgrade (`year_start` +
  `extract_case_series`). Requested by the PI.
- 2026-07-08: **Cost function folded into setup.** The targets the user gives now also specify the cost
  function — interview 1D + the research plan + Step-4 `targets.yaml` capture a `cost_config` (error_method,
  aggregation_method, tolerance) + optional per-target `cost_method`/`weight` (defaults `relative_error` +
  `rmsre` + ±20%), validated by `validate_targets_config.py`. Paired with the `evaluate_case.py`
  reconciliation so both scoring paths honor it. Requested by the PI.
- 2026-07-08: **Research-plan confirmation gate before building (Step 4).** After the interview + milestone,
  the agent now drafts `$A2MC_ROOT/use_cases/$SITE/research_plan.md` (goal, granularity, targets, mode,
  milestone, PFTs or ecosystem-only, parameter approach, seed, open gaps), presents it, and gets the user to
  **confirm** before any config is written; only on confirmation does it record the case memory + propagate
  the plan into the config files. **Path-safety:** all writes are anchored to `A2MC_ROOT` (derived via
  `git rev-parse --show-toplevel` — it is unset on a first run, and a bare `$A2MC_ROOT/use_cases/$SITE` with
  an empty prefix would write to the filesystem root). New footguns (building before confirmation; bare
  relative path from the wrong cwd). Requested by the PI.
- 2026-07-08: **Goal-and-data-first interview + guided path for users new to FATES.** Restructured Step 1 to
  lead with the science goal + **target granularity** (1.0) and a data-inventory helper (1.1): an
  **ecosystem-level** goal (e.g. MODIS/tower GPP) does NOT require enumerating dominant PFTs or per-PFT
  biomass, so PFT identification (1.2) + the 1C PFT questions are now conditional on PFT-level targets. Added
  a **path choice** (know-your-setup vs guided). New footgun (over-asking a new user for detail they don't
  need). Cross-linked the operating-discipline stance (`AGENTS.md` §Offline-Agent Operating Discipline +
  `feedback_offline_agent_operating_discipline`). Requested by the PI.
- 2026-07-07: **Parameter-list building (Step 4b).** Interview D reworded to "do you have an initial list of parameters to be calibrated?" with a 3-case branch (vetted / rough / none). Added **Step 4b** — when the user has no list (or a rough one), the agent studies the mechanisms via `HybridRetriever.get_calibration_context()` + curated `curated_relationships_<profile>.yaml` + the CNP calibration guide + Adaptive Memory to build a target-driven list with source-anchored bounds (no fabricated values), presented for review before writing; a vetted list gets a coverage check instead. New footgun (list-from-names / fabricated bounds). Requested by the PI.
- 2026-07-07: Initial version — official first-run setup flow for the offline agent (interview → verify checkout/milestone → create + populate use case → hand off to phase0-design). Fills the gap between "cloned the repo" and `phase0-design`; complements `onboard-session` (which assumes an existing setup). Requested by the PI.
