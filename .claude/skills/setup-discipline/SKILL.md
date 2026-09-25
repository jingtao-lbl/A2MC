---
name: setup-discipline
visibility: public
category: calibration
description: The per-STAGE definition-of-done checklist for the setup arc — is a2mc-init, onboard-model, or onboard-case actually finished, or does it only look finished? Use at the start of any setup stage and again before declaring it done, and when a session inherits a half-built clone and must find what is missing. Answers "which stage am I even in" (is the model onboarded, does the checkout match a registered RAG milestone, is there a real use case), then gives that stage's full checklist with the executable gate for every item that has one. DISTINCT from the stage skills themselves (which PERFORM the work) and from calibration-discipline (the per-cycle/per-round checklist for a campaign already running) — this is the same habits layer, one stage earlier.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [setup]
  summary: "Per-stage definition-of-done checklists for the setup arc (a2mc-init / onboard-model / onboard-case), with the executable gate for each item. The setup-side counterpart of calibration-discipline."
---

<!-- ─────────────────────────── At a glance ─────────────────────────── -->
```text
Which setup skill, in the order a user meets them (python3 tools/check_stage_ready.py says which):

  clone not wired ........................ a2mc-init Step 1        (EVERY user, first)
  model A2MC does not have ............... a2mc-init Steps 0,1,3 → onboard-model      (Stage 2)
  model A2MC has, not built/verified here  a2mc-init Step 2                           (Stage 1)
  a case to create, or one still in setup  onboard-case  (resume at its first failing row)  (Stage 3)
  a case with workflow state ............. onboard-session  (not setup)

The stage NUMBERS are the router's labels (1 a2mc-init, 2 onboard-model, 3 onboard-case,
4 onboard-session), not the order: a new-model user does Stage 1's Step 1 before Stage 2.
Each stage below is DONE only when every [ ] is checked or explicitly N/A with a reason.
```

# setup-discipline — is this setup stage actually finished?

The setup skills name dozens of gates and tools, all inline in their steps. That makes each stage easy to
*perform* and hard to *finish*: nothing collects "what does done mean here", so a stage gets abandoned
mid-way and the next session inherits a clone that looks configured and is not.

This skill is the collector. It does not re-teach the stages — each item points at the step or tool
that owns it, named by skill and step.

**Why a stage half-done is worse than not started:** the failure is silent. An unwired clone commits with
the repo's checks off; an unmatched milestone is invisible until the RAG answers in another model's
vocabulary; a `targets.yaml` still holding template values is invisible until Phase 2 scores nothing.
Each is cheap to check now and expensive to discover later.

## Step 0 — establish which stage you are in (do this first, always)

One command reads it from disk and needs **nothing sourced**:

```bash
python3 tools/check_stage_ready.py                 # auto: per-clone rows, the stage, NEXT, cases still in setup
python3 tools/check_stage_ready.py --model ecosim  # one model's onboarding (Stage 2)
python3 tools/check_stage_ready.py --case EcoSIM_BioCON   # one case (Stage 3)
```

It prints the per-clone rows at **every** stage, a `NEXT:` line naming the skill to run, and the items
it cannot verify as `?` lines, so a clean run is never mistaken for a finished stage. Under Claude Code
the `SessionStart` hook prints the same answer at session start (`⚠ THIS CLONE IS NOT FULLY SET UP` for
the per-clone rows, `► SETUP STAGE N` otherwise), and a `PostToolUse` hook re-reports it when an action
crosses a stage boundary (a case scaffolded, a site config or parameter list written, a milestone
registered, or an onboard-model build step for a named model). Any other harness runs the command.

| what you find | stage | skill |
|---|---|---|
| any per-clone row ✗ | — | `a2mc-init` Step 1 first, whatever the stage |
| the user's model has no adapter, or `check_stage_ready.py --model <m>` shows a stage-2 ✗ (ATS today) | **2** | `a2mc-init` Steps 0, 1 and 3, then `onboard-model` (or resume it at its first ✗) |
| model onboarded, `use_cases/` holds only templates | **1** | `a2mc-init` from Step 2, then `onboard-case` |
| a real case with no workflow state | **3** | `onboard-case`, resuming at `--case <Case>`'s first ✗ |
| a real case **with** workflow state | — | not setup: `onboard-session` |

**Mid-stage is the common case, not the exception.** Resume the stage's owner at its first failing row;
do not restart the stage, and do not hand a half-built case to `onboard-session`, which only resumes a
case that has reached Phase 0.

---

## Stage 1 — `a2mc-init` is DONE when

The per-CLONE half, plus the model install on this machine. Owns the clone, the machine config and
the routing — **not** the case.

- [ ] **Name recorded** — `python3 tools/whoami.py --verbose` resolves from `.me` (Step 0). A user who
      declines has `A2MC user` recorded, never nothing.
- [ ] **Clone wired** — `python3 tools/check_clone_setup.py` exits 0 (Step 1). Its rows: git hooks,
      chroma skip-worktree, memory symlink, author name, and on NERSC a temp directory inside `$HOME`.
- [ ] **GitHub question asked** and the answer taken (Step 1). [human]
- [ ] **Model identified**, and a model A2MC does not have routed to `onboard-model` after Steps 1 and 3
      (Step 0). CIME users told about `A2MC-elm`.
- [ ] **Locations asked, not assumed** (Step 2.1) — where the model's source checkout is, or where to
      clone it, and the archive root for built binaries. [human]
- [ ] **Model built on this machine and archived** (Step 2.1, from `models/<m>/BUILD.md`) — or N/A for
      ELM-FATES, which CIME builds per case. The test is the binary, never the build script's exit code.
- [ ] **Checkout verified** (Step 2.2) — `scripts/rag_match.py` (ELM) or `tools/model_preflight.py`:
      exit 0 match or 3 **drift** (proceed, and say so). Exit 2 routes to `onboard-model`; exit 1 means
      no version was read. Report the commit and the verdict to the user.
- [ ] **Fork-safe remotes offered** (Step 2b) — required only before editing model source; a user
      with no fork gets the push sentinel at most, and a decline is fine. The checker reports it as ℹ.
- [ ] **The RIGHT machine config** (Step 3) — `a2mc_config.sh` for CIME, with every shipped value
      checked; `a2mc_noncime_config.sh` otherwise, which holds no model path, binary or account.
- [ ] **Routed onward explicitly** (Step 4) — the router's `NEXT:` line named to the user, with the
      model's runbook skill. A2MC's front door ends by handing off, never by trailing off.

> `A2MC_MODEL_PATH` is **not** a Stage-1 item. For EcoSIM, PFLOTRAN and ATS a case's site config sets
> it (`onboard-case` Step 2); for ELM-FATES it defaults to `A2MC_E3SM_ROOT` in `a2mc_config.sh`.

---

## Stage 2 — `onboard-model` is DONE when

The per-MODEL half, and the longest. Its own arc table is the authority; this is the definition of done
over it. **Precondition: the clone is wired** (`a2mc-init` Step 1) and the machine config for the model's
family written (`a2mc-init` Step 3).

**What the modeler brings, and what Step 0d produces.** A filled questionnaire guides the agent (no
script reads it). The source tree at a known commit is needed. A parameter file, a sample output and a
run recipe are what Step 0d **produces** with a user who does not have them yet; they are not an entry fee.

- [ ] **Locations asked, not assumed** (Step 0a) — the source checkout (or where to clone it), the
      archive root, a run directory for the orientation run, and on a cluster the account. [human]
- [ ] **Fork-only push guard on the model checkout** (Step 0b) — `origin` push disabled, `fork` set,
      **both directions verified** with dry-run pushes; a user with no fork gets the sentinel only.
- [ ] **Codebase characterized** (Step 0c) before scaffolding — the seven questions answered in
      `models/<name>/README.md`.
- [ ] **Orientation run** (Step 0d) — the model built and its own sample case run with the user, the
      output opened, and the recipe recorded in **`models/<name>/BUILD.md`**. A tested blocker counts,
      recorded there with what was tried.
- [ ] `models/<name>/` **scaffolded** (`scripts/init_adapter.py --model <name>`).
- [ ] **Commit-pinned codebase wiki** exists (`generate-codebase-wiki`), and **V1** passes
      (`tools/validate_wiki_vs_source.py --model <name>`).
- [ ] **Real parsers** read the model's ACTUAL files; **V4** adapter conformance ≥ Yellow.
- [ ] **Curated seed** written, PI-in-the-loop, and **`tools/validate_seed_coverage.py`** passes: every
      category has a mechanism and every calibratable parameter is named by one. **V2** Green/Yellow.
- [ ] **RAG built AND the index actually committed** — `chroma.sqlite3` carries skip-worktree
      (`rebuild-rag`).
- [ ] **Milestone registered** in `rag/milestones.json` — what `model_preflight` matches against;
      without it every later user gets NO MILESTONE. **Then `model_preflight --checkout "$CHECKOUT"`
      reports match** (exit 0): the milestone resolves the checkout it was built from.
- [ ] **V3** RAG diff vs reference, including the FATES regression check.
- [ ] **Adaptive memory seeded** — `memory/<name>/gained_knowledge/discoveries.json` carries entries
      (`check_stage_ready.py --model <name>` row).
- [ ] Run template rendered + **V5** validated.
- [ ] **Smoke test** as the recipe states it (the offline chain on the model's sample outputs).
- [ ] **Case template authored** (step 14) — `use_cases/<Model>_template/` exists and
      `python tools/create_use_case.py --model <name> --case Demo --dry-run` resolves it.
- [ ] **Per-model scripts stay per-model** (PI rule).
- [ ] Handed off to **`onboard-case`** — an onboarded model with no case is not yet useful.

> Run `validate-rag-chain` (V1→V2→V3 in order) rather than the three validators by hand.

---

## Stage 3 — `onboard-case` is DONE when

The per-CASE half, repeatable for every new site/project on an already-onboarded model.

- [ ] **Target granularity established FIRST** (Step 1.0), in the model's own grammar — the
      `PFT<id>_<vartype>`/SZPF forms are ELM-FATES's; an adapter model uses `variable`/`reduce`/
      `window_years` against its own output registry.
- [ ] **Group identity from the model's own registry, never from names** — for FATES the PFT inventory
      in Step 2; for an adapter model the legal names from its output registry. N/A for ecosystem goals.
- [ ] **Calibration vs validation data separated** — only calibration data enters `targets.yaml`.
- [ ] **This case bound to a verified model install** (Step 2) — `rag_match.py` / `model_preflight.py`
      run against **this case's** checkout, drift stated in the plan, an **archived** binary for a
      standalone model, and the output location and HPC account from interview round 1A recorded
      (`A2MC_OUTPUT_ROOT` or ATS's `A2MC_CASE_ROOT`, and `A2MC_HPC_ACCOUNT`). [human]
- [ ] **Scaffolded** as `use_cases/{Model}_{Case}/` via `tools/create_use_case.py` (Step 3; `--dry-run`
      first; never `cp -r`). The template copy is not a decision.
- [ ] **`research_plan.md` drafted and APPROVED** — ★ GATE 1 (Step 4). No **value** goes into the site
      config, `targets.yaml` or the parameter list before this.
- [ ] **Setup session log** written with `calibration-log` when the plan was confirmed (Step 4(a)).
- [ ] **Every template placeholder replaced** — the `check_stage_ready.py --case` row passes.
- [ ] **Parameter list built or vetted from the mechanisms** (Step 4b), priors from **this model's**
      knowledge store, `bound_source` per parameter. ★ GATE 2. The SALib file is Phase 0's to write.
- [ ] **`calibration_rounds.yaml`** generated with **this model's** generator and checked (item 3b).
- [ ] **`tools/check_setup_ready.py` exits 0** (Step 5) — N/A is a pass and `!` (drift) does not block;
      a ✗ is not.
- [ ] **Handed off to `phase0-design`** with the ensemble scheme + size agreed, and the model's runbook
      and monitoring skill named (Step 6).
- [ ] **No auto-memory written about this case.** Case state belongs in the case's `gained_knowledge/`,
      `workflow_state_offline_r{NN}.json`, or `TODO.md`.

---

## The rule that outranks the lists

**A checked box means you ran the check, not that you believe the item holds.** Every line above with
a tool named is executable; the ones marked [human] or without a tool are the ones to state explicitly as
done or N/A, with the reason, in the stage's log. An unrunnable claim recorded as "done" is how a
half-built clone looks finished. `check_stage_ready.py` runs the executable subset; its `?` lines list the
rest.

## Cross-references

- `a2mc-init` · `onboard-model` · `onboard-case` — the skills that PERFORM these stages
- `calibration-discipline` — the same habits layer for cycles and rounds, once setup is done
- `onboard-session` — for a case with workflow state, not a setup stage
- **`tools/check_stage_ready.py`** — the executable half of THIS skill (routing + the mechanical subset)
- `tools/check_clone_setup.py` · `tools/model_preflight.py` · `scripts/rag_match.py` ·
  `tools/check_setup_ready.py` — the gates the items name
- `models/<name>/BUILD.md` — each model's build recipe
- Memory: `feedback_two_machine_configs_cime_vs_noncime`, `feedback_model_source_push_fork_only`,
  `feedback_no_case_state_in_memory`, `feedback_per_model_scripts_not_generic`

