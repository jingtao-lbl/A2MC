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
Which stage am I in?  ─┬─ model NOT onboarded ................ Stage 2  onboard-model
                       ├─ onboarded, clone NOT configured .... Stage 1  a2mc-init
                       ├─ configured, need another case ...... Stage 3  onboard-case
                       └─ configured + a case in flight ...... (not setup) onboard-session

Each stage below is DONE only when every [ ] is checked or explicitly N/A with a reason.
```

# setup-discipline — is this setup stage actually finished?

The three setup skills between them name **47 gates** and invoke **33 distinct tools**, all inline
in their steps. That makes each stage easy to *perform* and hard to *finish*: nothing collects "what does
done mean here", so a stage gets abandoned mid-way and the next session inherits a clone that looks
configured and is not.

This skill is the collector. It does not re-teach the stages — each item points at the step or tool
that owns it.

**Why a stage half-done is worse than not started:** the failure is silent. A missing fork-guard is
invisible until someone pushes to upstream; an unmatched milestone is invisible until the RAG answers
in another model's vocabulary; a `targets.yaml` that never mapped to output variables is invisible
until Phase 2 scores nothing. Each is cheap to check now and expensive to discover later.

## Step 0 — establish which stage you are in (do this first, always)

**The `SessionStart` hook surfaces this automatically** when the clone is not yet configured — it
prints `► SETUP STAGE N — start with the <skill> skill` and points here, and stays silent once setup
is done. Until 2026-08-19 nothing did: every other line of the session snapshot presumes a configured
clone, so a new user got a near-empty snapshot and no hint that `a2mc-init` exists.

**And it is re-surfaced whenever the stage ADVANCES** — a `PostToolUse` hook watches the actions
that cross a stage boundary (a case scaffolded, a site config / `targets.yaml` / parameter list
written, a milestone registered) and re-reports the stage with the items still outstanding. It
fires on the transition, not the state, so a run of writes inside one stage stays quiet. Without
it the SessionStart answer goes stale within the hour and nothing observes the moment it does.

**One command does the routing and the mechanical half of the checklist:**

```bash
python3 tools/check_stage_ready.py            # auto-detect stage + audit it
python3 tools/check_stage_ready.py --model ecosim
python3 tools/check_stage_ready.py --case EcoSIM_BioCON
```

It needs **no sourced config** (that is the point — `check_setup_ready.py` cannot run before a site exists), reports `✗` per failed item, and prints the items it *cannot* verify so a clean run is never mistaken for a finished stage. The lists below are the full contract; the tool is the checkable subset of them.

Do not assume from what the user says they want; three of these are checkable on disk.

```bash
ls models/                                       # is their model adapted at all?
python3 -c "import json;print(list(json.load(open('rag/milestones.json'))['milestones']))"  # profiles
ls use_cases/                                    # only TEMPLATE/ + *_template/ = no real case yet
python3 scripts/rag_match.py                     # does THIS checkout match a registered milestone?
```

| what you find | stage | skill |
|---|---|---|
| no `models/<name>/`, no milestone entry | **2** | `onboard-model` **first** — `a2mc-init` Step 0 says STOP |
| model onboarded, but `use_cases/` holds only templates | **1** | `a2mc-init` |
| a real `use_cases/{Model}_{Case}/`, user wants another | **3** | `onboard-case` |
| a real case **and** `workflow_state_offline_r*.json` | — | not setup: `onboard-session` |

**Mid-stage is the common case, not the exception.** If config exists but the site is half-built, do
the missing items here and then route to `onboard-session` — do not restart the stage.

---

## Stage 1 — `a2mc-init` is DONE when

The per-CLONE half. Owns the machine, the checkout, and the routing — **not** the case.

- [ ] **Model confirmed onboarded** before anything else — a brand-new model routes to Stage 2 first (Step 0).
- [ ] **Checkout verified + milestone MATCHED** — `scripts/rag_match.py` (FATES/ELM) or
      `tools/model_preflight.py` (generic, exit 2 = no match → `onboard-model`). Report the detected
      commits **and** the matched profile to the user; do not silently accept a near-match.
- [ ] **Distinguish the two no-match cases** — drift within a known model vs an unsupported model.
      They route differently (Step 2); conflating them sends a user to the wrong skill.
- [ ] **Fork-safe remotes offered** on the model checkout (Step 2b) — `origin` push disabled, `fork`
      set. Verify **both** directions, not just that the remote exists.
- [ ] **Machine config written** (Step 3) — and the RIGHT one: `a2mc_config.sh` for CIME-driven
      models, `a2mc_noncime_config.sh` for non-CIME adapter models. Picking the wrong one is a known
      adapter-branch failure.
- [ ] **`A2MC_MODEL_PATH` set** and pointing at the checkout that was just verified.
- [ ] **Routed onward explicitly** (Step 4) — say which stage comes next and why. A2MC's front door
      ends by handing off, never by trailing off.
- [ ] Setup captured in a **`calibration-log` session log** under `use_cases/{Model}_{Case}/memory/logs/`
      once a case exists — mode, checkout, milestone, decisions.

> **N/A rules.** Fork-safe remotes are N/A when the user has no write access to the upstream at all.
> Nothing else here is optional.

---

## Stage 2 — `onboard-model` is DONE when

The per-MODEL half, and the longest. Its own arc table (14 steps) is the authority; this is the
definition of done over it.

**Preconditions — refuse to start without them (Step 0):**

- [ ] Filled **questionnaire**; `init_adapter.py` refuses a required field set to `[unsupported]`.
- [ ] **Source tree at a known commit** — the wiki is commit-pinned, so an unpinned tree makes every
      citation unverifiable.
- [ ] A real **parameter file** and a real **sample output** file.
- [ ] A **run recipe** — HPC job template or local command.

**Guard before building anything (Step 0b):**

- [ ] **Fork-only push guard wired on the model checkout, BEFORE any other step** — `origin` push
      disabled, `fork` remote set, **both directions verified**. This is the one item whose omission
      can damage something outside A2MC.

**The chain — each link has its own validator, and a Yellow is a decision, not a pass:**

- [ ] **Codebase characterized** (Step 0c) before scaffolding — language, layout, parameter/output
      mechanics, run model.
- [ ] `models/<name>/` **scaffolded** from `_template/` (`scripts/init_adapter.py`).
- [ ] **Commit-pinned codebase wiki** exists (`generate-codebase-wiki`).
- [ ] **V1** wiki ↔ source — `codebase_wiki_validator.py` Green/Yellow.
- [ ] **Real parsers** — `parameter_parser.py` + `output_parser.py` parse the model's ACTUAL files,
      not the template's examples.
- [ ] **V4** adapter conformance ≥ Yellow.
- [ ] **Curated seed** written, PI-in-the-loop (`curated_seed_builder.py` / `inject-knowledge`).
- [ ] **V2** curated-YAML ↔ wiki Green/Yellow.
- [ ] **RAG built AND the index actually committed** — `chroma.sqlite3` carries `skip-worktree`, so a
      plain `git add` stages nothing and a rebuild is silently lost (`rebuild-rag`).
- [ ] **Milestone registered** in `rag/milestones.json` — this is what makes Stage 1's match succeed;
      skip it and every future clone reports "unsupported model".
- [ ] **V3** RAG diff vs reference, **including the FATES regression check** — onboarding a model must
      not degrade an existing one.
- [ ] Adaptive memory seeded (`memory/<name>/gained_knowledge/`).
- [ ] Run template rendered + **V5** validated (`{{VAR}}` all resolved).
- [ ] **Smoke test** — orchestrator dry-run through Phases 0–2, reasoning phases actually run.
- [ ] **Per-model scripts stay per-model** (PI rule) — a model-touching script is `*_<model>.py`,
      parallel to its siblings; only A2MC's own machinery is generic.
- [ ] Handed off to **`onboard-case`** — an onboarded model with no case is not yet useful.

> Run `validate-rag-chain` (V1→V2→V3 in order) rather than the three validators by hand.

---

## Stage 3 — `onboard-case` is DONE when

The per-CASE half, repeatable for every new site/project on an already-onboarded model.

- [ ] **Target granularity established FIRST** (Step 1.0) — ecosystem-level vs per-group. This decides
      everything downstream, and the grammar is **per model**: the `PFT<id>_<vartype>`/SZPF forms are
      ELM-FATES's. An adapter model uses `variable`/`reduce`/`window_years` against its own output
      registry. Ask granularity in the model's own terms.
- [ ] **Group identity mapped from the model's own registry, never from names** — for FATES, PFT ids
      read out of the base parameter file (`get_pft_names_from_file()`); for an adapter model, the
      legal names from its output registry. N/A for ecosystem-level targets.
- [ ] **Calibration vs validation data separated** — only calibration data enters `targets.yaml`;
      validation data stays in its native format and is never scored.
- [ ] **`research_plan.md` drafted and APPROVED** — ★ GATE 1. Nothing is written into
      `a2mc_config.sh` / the site config / `targets.yaml` before this.
- [ ] Case scaffolded as **`use_cases/{Model}_{Case}/`** via `tools/create_use_case.py` (`--dry-run`
      first; it never overwrites, and there is deliberately no `--force`).
- [ ] **Parameter list built or vetted from the mechanisms** (Step 4b), with `bound_source` recorded
      per parameter — measurements / literature+DOI / data centre. ★ GATE 2.
- [ ] **`calibration_rounds.yaml`** present and consistent with the config.
- [ ] **`tools/check_setup_ready.py` exits 0** — the goal-conditional preflight. N/A is a pass; a FAIL
      is not. Run the model's own targets validator directly when it reports `✗`, since the gate only
      reports pass/fail.
- [ ] **Handed off to `phase0-design`** with the ensemble scheme + size agreed.
- [ ] **No auto-memory written about this case.** Case state belongs in the case's
      `gained_knowledge/`, `workflow_state_offline_r{NN}.json`, or `TODO.md`.

---

## The rule that outranks the lists

**A checked box means you ran the check, not that you believe the item holds.** Every line above with
a tool named is executable; the ones without are the ones to state explicitly as done or N/A, with the
reason, in the stage's log. An unrunnable claim recorded as "done" is how a half-built clone looks
finished.

## Cross-references

- `a2mc-init` · `onboard-model` · `onboard-case` — the skills that PERFORM these stages
- `calibration-discipline` — the same habits layer for cycles and rounds, once setup is done
- `onboard-session` — for a configured clone with work in flight, not a setup stage
- **`tools/check_stage_ready.py`** — the executable half of THIS skill (routing + the mechanical subset)
- `tools/check_setup_ready.py` · `tools/model_preflight.py` · `scripts/rag_match.py` — the later, per-site gates
- Memory: `feedback_two_machine_configs_cime_vs_noncime`, `feedback_model_source_push_fork_only`,
  `feedback_no_case_state_in_memory`, `feedback_per_model_scripts_not_generic`

