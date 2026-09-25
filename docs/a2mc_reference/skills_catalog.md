# A2MC Skills — Capability Catalog

The **capability catalog** of the A2MC interactive (offline) agent. Each skill is a
folder under [`.claude/skills/`](../../.claude/skills/) containing a `SKILL.md` with
YAML frontmatter (`name`, `description`, `modes`) and an action-oriented body. A
coding-agent harness auto-discovers them and matches a user request against the
`description` trigger to decide which skill to invoke.

This catalog is the human- and agent-readable index: what each skill does, when to
invoke it, **which run configurations it applies to**, and the repo tools it drives.
See [`AGENTS.md`](../../AGENTS.md) for the operating contract these skills run under.

> **Mode-aware:** A2MC runs many configurations (ELM with or without FATES, different
> FATES API milestones, ECA vs RD nutrient schemes). Each skill declares a `modes:`
> block; before mode-specific steps, resolve the active configuration with
> `python tools/describe_mode.py` and honor the skill's applicability — skip or branch
> when the case's mode does not satisfy it.

> **When to invoke a skill:** when a request matches a skill's trigger **and** the active
> mode satisfies its `modes:` block, invoke the skill **before** improvising. Each one
> encodes conventions (case-naming, dedicated experiment directories, reproducibility
> gates, contamination guards) that are easy to get wrong from first principles.

---

## Skills (mode-agnostic — available now)



### `create-project-agent`
- **Purpose:** Stand up a **project agent**: an `A2MC-<Name>` repo whose **framework half arrives by sync and is replaced on
  every run**, and whose **one** top-level `<ProjectName>/` folder holds everything the project authors. A2MC's
  harness engineering — the board, both hook kinds, the log contract and its checkers, the memory bucket, the
  skills discipline — is reusable independently of calibration, and this packs it for one project.
- **Invoke when:** a project has **calibration as one step among others**, or **no calibration at all**. Nothing
  here is needed to simply *use* A2MC for calibration; that is `a2mc-init` / `onboard-model` / `onboard-case`.
  A project is the fifth unit of work and the only one that owns a repo topology.
- **Modes:** any — repo topology and the project-folder contract; model-agnostic and calibration-optional.
- **Backing tools:** `scripts/wrap_for_project_agent.sh` (`--init` / `--refresh`), `scripts/_wrap_scaffold.sh`,
  `tools/skill_models.py`, `tools/check_clone_setup.py`,
  `scripts/setup_clone.sh`, the destination's own setup checker.
- **Key discipline:** every path both halves write is a named conflict surface with exactly one of three
  resolutions — MERGE, DESTINATION_OWNED, or framework-owned — and the **separation manifest** is signed before
  any file is written. Protection is established BEFORE the first sync, because forward-only means an exclude
  retracts nothing. Git hooks **chain** rather than replace. A filtered copy cannot satisfy the framework's own
  checkers, so the destination is marked at seeding.



### `calibration-log`
- **Purpose:** Log interactive calibration/exploration work for a site under
  `use_cases/{Model}_{Case}/memory/logs/` — a PHASE log via `tools/phase_logger.py` (identical to the
  autonomous agent) or a free-form SESSION log, so both modes' logs synthesize together.
- **Invoke when:** "log this / this phase / this diagnosis / this experiment", "log this calibration session", "write a session log", "record what I explored".
- **Modes:** `any` — model-agnostic (PhaseLogger).

### `restart-failed-jobs`
- **Purpose:** Restart SLURM jobs that failed in an ensemble/experiment. Diagnoses failure
  mode first (infrastructure → restart-eligible vs model failure → archive), handles
  two-wave zombie cleanup, generates an audit TSV + flat case-list, and submits the
  restart via `phases/phase0_design/submit_phase0.py --cases-file`.
- **Invoke when:** failures appear mid-run (NODE_FAIL, PartitionDown, SIGKILL clusters) or
  at end-of-run; "restart the failed jobs", "which failures are restart-eligible".
- **Modes:** `any` (HPC) — the SLURM restart workflow is model-agnostic. The model-failure
  fingerprints in Step 2 are FATES examples; a different model has different abort signatures.
- **Backing tools:** `tools/diagnose_ensemble_status.py`, `tools/validate_restart_script.py`,
  `phases/phase0_design/submit_phase0.py`.

### `restart-adapter-ensemble`
- **Purpose:** Recover failed cases in a **non-CIME adapter-model ensemble** (EcoSIM, PFLOTRAN, ATS) — classify why each case died, persist the failed-case list, and relaunch only what is missing. The counterpart to `restart-failed-jobs`, which is ELM-family/CIME-shaped by its own admission.
- **Invoke when:** "which cases failed", "rerun the failed cases", "restart the crashed runs", "the ensemble has holes", or before any sensitivity analysis — a crashed case is a **hole** in a Saltelli design, while a finished-but-degenerate case is a valid data point.
- **Backing tools:** `tools/model_ensemble_status.py` (reconciles the scheduler against the model's own completion check — pass `--ensemble-jobs` for an array or task-farm, which write no per-case `job_id.txt` and would otherwise leave dead cases reported as `RUNNING`), each model's `backend.check_case_status()`, `sacct -P` for step-level exit codes.
- **Key discipline:** the **exit code lies** — measured on EcoSIM R3, `sacct` reported COMPLETED for all 11,425 cases while 853 had not finished, because the model's `ENDRUN` exits 0 and its history tape is created at initialisation. Completion is the model's **end-of-run artifact**. The same crash is also recorded differently by submission arm (direct exec `rc=136` vs an `srun` step's `ExitCode 0:8`), and `sacct` must be read with `-P` or truncation drops every array task ≥ 1000. Persist the case **list**, not a count; relaunch idempotently; and where a model fix is involved, pass the V0 / inertness / efficacy gates first.
- **Modes:** `any` — the non-CIME adapter models; no FATES dependency.

### `arm-hpc-monitoring`
- **Purpose:** At session start (or after compaction), detect live long-running login-node
  processes and arm Claude `Monitor` tasks on each long-running log with the right event +
  error filters (silence ≠ success), reacting with proposals rather than just relaying.
- **Invoke when:** a session begins/resumes while an ensemble round is in flight, or right
  after launching a new submitter/restart job.
- **Modes:** `any` (HPC) — monitors any in-flight A2MC ensemble/experiment; model-agnostic.

### `arm-local-monitoring`
- **Purpose:** Watch an ensemble running on a WORKSTATION with no scheduler — arm a `Monitor`
  on the dispatcher log a local submission writes, take liveness from the process table and the
  filesystem, and say which of the HPC watcher contract does not transfer.
- **Invoke when:** after an `A2MC_EXEC_MODE=local` submission, when resuming a session with
  local runs in flight, or when someone asks how to monitor a run on their own machine.
- **Modes:** `any` (local) — the no-scheduler counterpart of `arm-hpc-monitoring`; model-agnostic.
- **Backing tools:** the dispatcher artefacts (`local_dispatch.log`, `local_cases.txt`, and the
  dispatcher PID inside each `job_id.txt`), `ps`, and the backend's own `check_case_status`.
- **Key discipline:** most of the three-layer watcher contract does NOT port — its heartbeat
  check is scheduler-aware, and a watcher whose only job is to look at what is already visible
  would itself need a liveness check. What DOES port is that silence on a crash is identical to
  silence on a long run, so the filter carries a progress signal alongside error signatures, with
  `Killed` and `Cannot allocate` added because the OOM killer has no scheduler to record it. The
  dispatcher exiting is not completion; completion is `check_case_status` over every case.

### `a2mc-init`
- **Purpose:** First run in a **clone** — the per-clone half of getting started. Greets + gauges
  experience and records the user's name, **wires the clone** (`scripts/setup_clone.sh`, gated by
  `tools/check_clone_setup.py`; every user, before any routing), gets the model **built and verified
  on this machine** (`models/<m>/BUILD.md`; `rag_match.py` for ELM, `model_preflight.py` otherwise,
  where drift is a warning, not a stop), offers fork-safe remotes on the checkout, writes the machine
  config (`a2mc_config.sh` or `a2mc_noncime_config.sh`), then **routes** to `onboard-model` (new model)
  or `onboard-case` (new case). It does **not** create a use case — that moved to `onboard-case` on 2026-08-02 so a
  second case has an entry point.
- **Invoke when:** "set up A2MC", "first time using A2MC", "help me get started / onboard me to
  A2MC", "configure A2MC on this machine", "wire up my clone", or when the session snapshot reports
  the clone is not fully set up.
- **Modes:** `any` — model-agnostic. **Distinct from `onboard-session`**, which resumes an
  already-configured setup, and from `onboard-case`, which does the per-case work.

### `onboard-case`
- **Purpose:** Create a **new case/project** for a model that is already onboarded — the
  repeatable half of getting started, run again for every site, project or scenario. Interviews
  from the science goal (target granularity → data inventory → grouping identity), drafts a
  `research_plan.md` the user confirms (GATE 1), scaffolds `use_cases/{Model}_{Case}/` from **that
  model's** site-agnostic template, populates the site config + `targets.yaml`, builds or vets the
  parameter list (GATE 2), generates the round record, runs `check_setup_ready.py`, and hands off
  to `phase0-design`.
- **Invoke when:** "set up a new case", "add a site/project", "onboard my case", "calibrate
  <model> at <site>", "start a second case"; and automatically after `onboard-model` finishes.
- **Modes:** `any`. **Requires the model to be onboarded first** — it refuses and routes to
  `onboard-model` otherwise. Extracted from `a2mc-init` (audit `20260802e`).

### `onboard-session`
- **Purpose:** Cold-start runbook — orient at the start of a session or after a context
  reset/compaction (read the most recently changed calibration log and the case's offline
  workflow state, re-read CLAUDE.md, check live HPC processes + run state, check pending
  knowledge), delegating to `arm-hpc-monitoring` / `curate-knowledge`.
- **Invoke when:** a session begins/resumes/compacts; "catch up", "where did we leave off", "onboard".
- **Modes:** `any` — model-agnostic. Pairs with the `SessionStart` hook. For a **first-run** (no
  config yet), use `a2mc-init` instead.

### `calibration-goal`
- **Purpose:** The offline **run-to-convergence DRIVER** — the conductor above the phase skills
  (docs/38). Each invocation loads `WorkflowStateOffline`, resolves the next action, dispatches to the
  matching `phaseN` skill, advances + saves state, and repeats across turns + HPC waits until Phase-7
  CONVERGED or a loop limit. The offline analog of `orchestrator.py:1031`.
- **Invoke when:** "run/continue the calibration", "drive to convergence", "keep calibrating until the
  targets are met", or when a standing goal to reach the validation targets is set.
- **Backing tools:** `tools/workflow_state_offline.py` (`WorkflowStateOffline` + `resolve_next_action` +
  `validate_phase6_decision`); dispatches to `phase0-design`…`phase6-refinement`; `arm-hpc-monitoring`
  (the WAIT bridge); `summarize-calibration-round` (round exit).
- **Key discipline:** harness-neutral (no `/goal`/`Monitor` dependency — optional hardenings only);
  pause ONLY at the 4 human gates (Phase-6 decision, curated-KB write, expensive/irreversible, hard
  stop); `st.save()` after every advance.
- **Modes:** `any` — harness-neutral loop mechanics, model-agnostic.

### `setup-discipline`
- **Purpose:** The per-**stage** definition of done for the SETUP arc, the counterpart of
  `calibration-discipline` one stage earlier. The three setup skills name 47 gates and 33 tools inline across their
  steps, so a stage is easy to perform and hard to finish; this collects "what does done mean here" so a
  half-built clone stops being indistinguishable from a finished one.
- **Invoke when:** starting any of `a2mc-init` / `onboard-model` / `onboard-case`, again before declaring
  that stage done, or when a session inherits a half-configured clone and must find what is missing.
- **Backing tools:** `scripts/rag_match.py`, `tools/model_preflight.py`, `tools/check_setup_ready.py`,
  `tools/check_calibration_rounds.py`, the V1-V5 adapter validators via `validate-rag-chain`.
- **Key discipline:** establish WHICH stage you are in from disk (models/, rag/milestones.json,
  use_cases/) before trusting what the session says; a Yellow validator is a decision, not a pass; the
  two items that silently break every *later* clone are milestone registration and actually committing
  the RAG index (`skip-worktree` makes `git add` a no-op); a checked box means the check was RUN.
- **Modes:** `any` — model-agnostic.

### `calibration-discipline`
- **Purpose:** The per-cycle and per-round **definition of done** that keeps a long offline campaign
  stable — the invariant checklist of habits `calibration-goal` must honor so performance does not drift
  across cycles. Prevents the small, individually-invisible omissions (a missed monitor, a scratch-edited
  plot script, a skipped state-validate, a round summary with no next-round plan) that accumulate over 10+
  cycles.
- **Invoke when:** starting a multi-cycle offline calibration, and re-checked every cycle end / round end;
  or when the user asks to "keep performing stably" / "distill the calibration discipline".
- **Backing tools:** `tools/check_offline_log_evidence.py`, `tools/check_workflow_state_offline.py`;
  pairs with `calibration-log`, `arm-hpc-monitoring`, `write-report`, the `phase{0..6}` skills.
- **Key discipline:** self-documenting `phase_results/{stem}/` with the figure script canonical there;
  arm monitors right after every HPC launch (own jobs only); update + validate state after every phase;
  a synthesis report at each cycle end; drive to the loop limit; and a **round summary that MUST propose
  the next-round work plan** (param add/remove, bounds recenter, base update, residual split).
- **Modes:** `any` — model-agnostic.

### `curate-knowledge`
- **Purpose:** Review + promote staged Tier-3 knowledge proposals — the human-in-the-loop half
  of the memory write gate. Lists `auto_discovered_pending.json`, evaluates each against
  evidence, promotes vetted ones / discards misunderstandings (`tools/review_pending_knowledge.py`).
- **Invoke when:** "review/curate pending knowledge", "promote proposals", or at session start when staged proposals exist.
- **Modes:** `any` — model-agnostic. The interactive agent's job by design (curated writes are interactive-only).

### `round-housekeeping`
- **Purpose:** The POST-ROUND step between one round's human gate and the next round's Phase 0 —
  the one nothing used to schedule. Curates the round's Phase-5-verified findings into the SITE
  knowledge base (every refutation as its `(parameter, direction, base)` triple), promotes or
  discards the online agent's staged proposals, records the case's script templates, emits the
  open-questions list Phase 0 consumes, records which bounds are still `provisional:` debt, and
  ASSERTS the KB is non-empty where the round produced findings.
- **Invoke when:** "run the housekeeping", "close out the round", "curate this round's knowledge",
  or when `resolve_next_action()` returns `close("housekeeping")`.
- **Modes:** `any` — model-agnostic. SEQUENCES and VERIFIES; the procedures live in
  `phase6-refinement` Steps 3 and 3b. A CONVERGED round runs it too, with a **fuller** checklist:
  convergence is the campaign boundary and hands work to nobody.
- **Measured gap:** after three rounds and thirty experiment cycles one case's site KB held
  `experiments: []`, `failed_approaches: []`, `parameters: {}`.

### `diagnose-forensics`
- **Purpose:** Triage ONE suspicious result (outlier, too-good "best" case, small failure cluster,
  an impossible-looking number) — determine FIRST whether it is real or an artifact (contamination,
  infrastructure timing, mislabeled index, NaN, truncated output, stale run-state), then root-cause it.
- **Invoke when:** "why is case X an outlier", "is this real or contamination", "investigate this anomaly".
- **NOT for:** a whole round's failing targets, or ranked root causes across the ensemble — that is
  `phase3-diagnosis`. This skill is reactive and single-case; that one is proactive and round-wide.
- **Modes:** `any` — model-agnostic, with the CIME and adapter tool paths named in separate columns;
  the mechanism tools (carbon / mortality / nutrient / PFT) are FATES-shaped and have no adapter analog.

### `scientific-analysis`
- **Purpose:** A manuscript-supporting investigation that ends in a figure + an ana_log:
  pose a question → pull run data → compute the statistic/mechanism → make a figure → cite
  evidence → write an ana_log.
- **Invoke when:** "investigate whether X", "is X correlated with Y", "analyze the mechanism", "make a manuscript figure for X".
- **Modes:** `any` — model-agnostic; examples are FATES/Kougarok.

### `markdown-to-pdf`
- **Purpose:** Convert a markdown document (an ana_log, report, or note) to a shareable PDF
  or Word `.docx` via pandoc (+ a LaTeX engine for PDF; python-docx for round-trip-safe docx).
  Prose only — slide decks go through Marp. Self-contained repo copy (no user-level dependency).
- **Invoke when:** "convert/render markdown to PDF/Word/docx", "render this ana_log/report to PDF", "make a PDF of this", "turn this .md into a docx".
- **Modes:** `any` — model-agnostic.

### `literature-review`
- **Purpose:** Systematic, citation-backed literature review over academic databases via the `paper-search-mcp` server (search → triage → extract → cited synthesis). Two modes: PARAMETER-BOUNDS (a defensible `[lo, hi]` range for a FATES/ELM parameter, to refine a Phase-0 param list's `lower`/`upper` columns) and MANUSCRIPT (a themed topic review). Every citation is a validated, resolvable DOI — no fabrication.
- **Invoke when:** "lit review on X", "what's the published range for parameter X", "find bounds for X from the literature", "review papers on X", "synthesize the literature for". NOT a single-citation lookup.
- **Modes:** `any` — model-agnostic (needs the `paper-search-mcp` server). Pairs with `markdown-to-pdf` and `manuscript-writing-style`.

### `onboard-model`
- **Purpose:** Top-level adapter-kit orchestrator — take a NEW model (EcoSIM, CLM/CTSM, ATS, TEM,
  ReSOM, …) from a filled modeler questionnaire to a calibration-ready A2MC instance: scaffold the
  `models/<name>/` adapter package, build the knowledge chain (delegating the wiki→RAG→curated→validate
  sub-chain to `build-rag-from-scratch` et al.), register the version-association milestone, and
  smoke-test the reasoning phases.
- **Invoke when:** "onboard/couple/adapt <model> to A2MC", "fork A2MC for my model", "run the adapter
  kit for <model>", or driving the EcoSIM onboarding. NOT for reindexing an existing model (use
  `rebuild-rag`) or the RAG sub-chain alone (use `build-rag-from-scratch`).
- **Backing tools:** `scripts/init_adapter.py`, `models/_template/`, `scripts/curated_seed_builder.py`,
  the V1–V5 validators (`tools/*_validator.py`, `tools/rag_diff.py`), `rag/milestones.json`.
- **Key discipline:** knowledge-first/execution-last sequencing; the V4 parser-contract interface
  (no-arg `__init__` + `parse(file_path)`); parsers live at `models/<name>/`, not `rag/<name>_*`.
- **Modes:** `any` — model-agnostic. See `docs/A2MC_Adapter_Kit_Master_Plan.md`, `docs/17`, `docs/19`.

### `ecosim-version-drift`
- **Purpose:** Get usable calibration data out of a drifted/current EcoSIM checkout — the two ways a
  run fails to yield it. **(A) Input drift:** the built binary is NEWER than the staged pft input, so
  it ENDRUNs mid-read (`ncd_getvar…: Variable not found`) writing NO tape while Slurm reports
  `COMPLETED` → EVOLVE the input from a newer donor pft table (functional-analog by type flags).
  **(B) Missing outputs:** the run finishes but a calibration variable is absent because it is
  registered `default='inactive'` → activate it via `hist_fincl1`. Detect → fix → re-verify →
  CONFIRM by run in both.
- **Invoke when:** an EcoSIM run produced no tape; "IEBTYP / Variable not found" ENDRUN; after
  rebuilding EcoSIM at a newer commit; `evaluate`/`extract` KeyErrors on a target variable; before
  an ensemble on a drifted checkout.
- **Backing tools:** `tools/model_check_input_compat.py` (generic detect guard),
  `models/ecosim/tools/evolve_pft_input.py` (input remedy: auto missing-var discovery + type-flag
  analog scoring + `--analog` override), `hist_fincl1` in the run namelist (output activation).
- **Key discipline:** never fabricate values (source from a real newer donor table); the guard
  checks var *presence*, not correctness — CONFIRM BY RUN (Slurm `COMPLETED` ≠ tape written ≠ target
  vars present); a target missing from the tape is usually inactive-by-default, NOT renamed —
  source-verify before renaming.
- **Modes:** `EcoSIM` — EcoSIM-specific per-PFT input contract + inactive-by-default outputs; NOT
  model-generic (declined for `onboard-model`). Worked examples: `20260713a` (input), `20260713c` (output).

### `ecosim-trait-check-refine`
- **Purpose:** Check whether EcoSIM per-PFT trait *values* are physiologically appropriate, then refine
  them — the *value-appropriateness* counterpart to `ecosim-version-drift`'s *structure/completeness*. Wraps
  the EcoSIM developer's ecosim-agent skills (referenced in place by `$MODEL = ${A2MC_MODEL_PATH}` path,
  NOT ported): run `ecosim-plant-trait-sanity-check`'s deterministic checker on a run's `plant_trait.*.desc`
  dump → interpret `ERROR`/`WARN` → (optional) web-evidence layer via `ecosim-trait-deriver` → map flagged
  `.desc` codes back to the NC `pft_file_in` vars → refine the input → re-verify by run.
- **Invoke when:** an EcoSIM run finishes but the plant is dead/stunted/botanically-wrong and you suspect
  the parameter VALUES; vetting a pft input before an ensemble; "are these trait values reasonable / sane-
  check the plant params".
- **Backing tools:** `$MODEL/python_tools/.claude/skills/ecosim-plant-trait-sanity-check/scripts/check_plant_trait_desc.py`
  (deterministic checker + `--web-evidence`), `…/ecosim-trait-deriver` (literature evidence); the run
  namelist's `disp_planttrait=.true.` (emits the `.desc`); netCDF4 to patch the NC input.
- **Key discipline:** the `.desc` is decoded model OUTPUT — refine the NC *input*, the `.desc` re-verifies;
  a checker ERROR is plausibility not causality (an establishment-stage death sits UPSTREAM of leaf-physiology
  flags — check the seedling survives year 1 first); sign/convention flags (e.g. `RCS<0`) can be real
  old-input↔new-binary breaks (verify against source, not "the reference grew with it"); a passing checker ≠
  a live plant; reference the ecosim-agent skills by `$MODEL` path, never hardcode, never port.
- **Modes:** `EcoSIM` — a diagnostic, not a guaranteed fix. Distilled from the BioCON onboarding
  (`20260714f`, `20260715a` — the RCS-sign hypothesis, falsified).

### `plotting`
- **Purpose:** Produce a clean, readable, report/manuscript/slide-grade matplotlib figure (right fonts, no legend/annotation overlap, log scale + units, finding-stating title) and **verify it by viewing the saved PNG** before shipping.
- **Invoke when:** "plot X", "make a figure/chart", "the legend overlaps", "clean up this plot", "make this publication-quality", "the fonts are too small", "the labels are clipped".
- **Modes:** `any` — model-agnostic.

### `write-report`
- **Purpose:** Write a comprehensive, integrated, self-contained report for a zero-context human reader (outline → executive summary → sectioned narrative → embedded figures → skills and memory invoked → provenance; terms defined INLINE on first use, no glossary block since 2026-08-24), facts-first with cross-log contradiction reconciliation.
- **Invoke when:** "write a report", "write up X for the PI/collaborator", "make an integrated report on X", "summarize this investigation into a report". NOT a standardized round summary (`summarize-calibration-round`) or journal prose (`manuscript-writing-style`).
- **Modes:** `any` — model-agnostic.

### `build-rag-from-scratch`
- **Purpose:** Construct the RAG/GraphRAG knowledge layer from scratch (new model or fresh build).
- **Invoke when:** "build the RAG from scratch", "stand up RAG for <model>".
- **Modes:** `any` — model-agnostic. See `docs/a2mc_reference/rag_build_roadmap.md`.

### `build-surrogate`
- **Purpose:** Build, score and hand over a learned surrogate of a process model from a finished calibration ensemble: the S0/S1/S2/S3 tier ladder in `models/surrogate/`, its gated ascent, the hold-out design, and the acceptance and promotion gates.
- **Resolve the USE MODE first** — `offline_search` (a calibration accelerator, gated on RANKING against distance to the observation) and `online_inference` (an emulator, gated on pointwise daily R2 >= 0.9) are not interchangeable and a wrong choice yields a verdict about the wrong question.
- **The hold-out design is a PHASE 0 decision.** An independent validation lattice cannot be recovered by re-splitting one Sobol' sequence; it must be drawn with a different scramble seed and RUN. `A2MC_SOBOL_SEQ_VALID_SAMPLES` / `_SEED` / `A2MC_VALID_MATRIX_FILE` configure it.
- **Carries the measured traps:** a Sobol' tail block is the EASIEST hold-out and not a control; a Chebyshev "outer shell" degenerates to random past a few dimensions; a conservation law must be verified in the model's own output before a loss is built on it; and a case hold-out cannot establish an emulator claim (measured: three of five fluxes met the bar on held-out cases, zero of five on withheld YEARS).
- **Backing tools:** `scripts/check_surrogate_gate.py`, `scripts/fit_ensemble_surrogate.py`, `tools/promote_surrogate.py`, `tools/package_surrogate.py`, `models/surrogate/splits.py`.
- **Invoke when:** "build a surrogate", "train an emulator", "can we emulate this model", "speed up the search with a surrogate", or when asked whether a finished ensemble can support one.
- **Modes:** `any` — model-agnostic; `models/surrogate/` exists only on `adapter-kit`.

### `rebuild-rag`
- **Purpose:** Rebuild/refresh a model's RAG/GraphRAG index (wiki bump, or a `--graph-only` refresh after a curated-YAML injection), and **commit it successfully**.
- **One build script per model, with DIFFERENT flags** — FATES `scripts/build_rag_index.py`, EcoSIM `scripts/build_ecosim_rag.py`, PFLOTRAN `scripts/build_pflotran_rag.py`. Step 0 routes; do not copy a command between them (PFLOTRAN has no `--graph-only`, EcoSIM no `--test`, only FATES takes `--profile`).
- **Carries the commit trap:** `chroma.sqlite3` is tracked but `--skip-worktree` in every clone, so `git add` stages **nothing** and a rebuild is silently lost — how the 2026-08-01 PFLOTRAN rebuild vanished.
- **Invoke when:** "rebuild/refresh the RAG", "rebuild the EcoSIM/PFLOTRAN index", "the index is stale".
- **Modes:** `any` — the workflow is model-agnostic; the scripts are not.

### `wire-knowledge-graph`
- **Purpose:** Audit and fix **which relations** a model's knowledge graph actually carries from its curated seed, and prove a graph rebuild is purely additive.
- **The failure it owns is SILENT.** A seed field no builder pass reads produces no error, no `skipped edge` line and no count change, since counts do not fall when an edge is never created. It also passes `validate_curated_yaml.py`, which checks that names RESOLVE and never that anything consumes them. Measured on EcoSIM 2026-09-08: two relation blocks unread, 95 edges absent, among them the driver of a live round's binding target.
- **One `build_graph()` per model, and node identity differs** — FATES `rag/graph_builder.py`, EcoSIM `scripts/build_ecosim_rag.py`, PFLOTRAN `scripts/build_pflotran_rag.py`; only `FATESKnowledgeGraph` is shared. EcoSIM keys by bare Fortran name, PFLOTRAN by deck-card leaf with addresses attached. Do not merge them; do not edit `graph_builder.py` to fix an adapter.
- **Carries the additive-rebuild proof:** diff node by node and edge by edge, and require zero removals and zero pre-existing edge attribute changes — `networkx.add_edge` replaces attributes on a repeat, so a second pass silently relabels edges a count line cannot show.
- **Invoke when:** "the graph cannot reach X from Y", "add this relation to the graph", "audit the graph wiring", or a Phase 3/4 traversal from a scored output returns nothing.
- **Modes:** `any` — the workflow is model-agnostic; the builders and their seed field names are not.

### `generate-codebase-wiki`
- **Purpose:** Generate a source-grounded codebase wiki for a model (the substrate the RAG indexes).
- **Invoke when:** "generate the codebase wiki", "make a wiki for <model>".
- **Modes:** `any` — model-agnostic. See `docs/a2mc_reference/codebase_wiki_generation_roadmap.md`.

### `validate-rag-chain`
- **Purpose:** Validate the RAG chain with the three validators, in order, before shipping.
- **Invoke when:** "validate the RAG", "is the RAG chain sound".
- **Modes:** `any` — model-agnostic. See `docs/a2mc_reference/rag_validation_workflow.md`.

### `inject-knowledge`
- **Purpose:** Inject curated domain knowledge into the KB via the curated-YAML overlay (additive, evidence-backed).
- **Invoke when:** "inject this knowledge", "add a curated relationship".
- **Modes:** `any` — model-agnostic. See `docs/a2mc_reference/graphrag_curated_yaml_roadmap.md`.

### `port-param-file`
- **Purpose:** Port a calibrated/site-tuned parameter file across model/API versions — reads a source (tuned prior-version) file + the new-version default template, remaps PFT identity **by functional type** (not index/name), and transfers every overlapping tuned value into the new version's format+structure.
- **Invoke when:** "port/migrate/convert the param file to api-XX", "map parameters to the new version", "build the new-API base file from the tuned prior one".
- **Backing tools:** `tools/port_param_file.py` (`identity`/`port`/`verify` subcommands; version/format/param-list agnostic).
- **Key discipline:** run `identity` FIRST and resolve any `NAME MISMATCH` slot by functional intent (`--map`); port ONTO the target template so no registered param is missing (avoids the `check_var … not on dataset` runtime abort). Doctrine (why/which-values) lives in the memories it cites — thin by design.
- **Modes:** `any` — the port TOOL is parameterized (`--pft-dim`/`--id-var`) and runs against any model, so there is no runtime gate. Its **distribution** is narrower: `scope: [fates, calibration]` withholds it from a project that did not ask for FATES, because every worked path written here is FATES. Modes and scope answer different questions and this skill is the case that separates them.

### `add-skill`
- **Purpose:** Scaffold + register a new skill (correct frontmatter + `## Changelog`, both
  registries, the drift check), stopping for human review before commit.
- **Invoke when:** "add a skill", "scaffold a skill", "make this reusable as a skill".
- **Modes:** `any` — meta machinery, model-agnostic.

### `refine-skill`
- **Purpose:** Refine an existing skill from accumulated evidence, human-gated — gather signal,
  propose a SKILL.md diff with cited evidence, STOP for approval, then apply + append a `## Changelog` line.
- **Invoke when:** "refine the X skill", "the X skill should have caught Y", "review the skills".
- **Modes:** `any` — meta machinery, model-agnostic.

---

## FATES Morris-ensemble analysis (`requires_fates: true`)

These consume the mode-aware machinery (the case `targets.yaml`, api-aware parameter-file
handling, ECA/RD pathway) but assume a FATES Morris-ensemble calibration (PFT/SZPF outputs,
ADSP/RGSP/TRANS spinup, Morris μ*). The `modes:` gate keeps them out of ELM-only mode.

### `summarize-calibration-round`
- **Purpose:** One-round summary — whole-ensemble figures + an evaluation report (best case,
  targets met vs tolerance) + a sensitivity report + the round's **mechanism inventory** (what the
  round established about the system, each finding with a citation) → markdown/PDF. Targets from
  the case `targets.yaml`. A required step before the ROUND report, which does not derive them.
- **Invoke when:** "summarize round N", "report for R<N>", "how did R<N> do", "what did this round
  establish", "what did we learn this round".
- **Modes:** `requires_fates: false` — generic since 2026-08-24; the CONTRACT is model-agnostic and
  the figure/screen BACKEND is per model.

### `compare-calibration-rounds`
- **Purpose:** The cross-round **parameter ledger** (what every round did with each parameter) and
  the cross-round **mechanism ledger** (what the campaign now knows about the system, one row per
  established mechanism), plus performance and sensitivity across rounds. Required before EVERY
  round report including the first, where only the cross-round figures are not applicable.
- **Invoke when:** "compare rounds", "which round is best", "refresh the multi-round figure", "what
  have we learned about the system across rounds", "why was parameter X refuted".
- **Modes:** `requires_fates: false` — generic since 2026-08-24.

### `ecosim-run-workflow`
- **Purpose:** The EcoSIM (non-CIME) counterpart to `offline-testing-workflow` — design a probe or
  ensemble, materialize cases across EcoSIM's three parameter-file surfaces, validate before
  submitting, monitor, and score against each target's own `reduce`/`tape`.
- **Invoke when:** "run an EcoSIM experiment/probe/ensemble", "set up EcoSIM cases", "submit the
  EcoSIM array", "why did my EcoSIM cases fail", "score the EcoSIM run".
- **Key discipline:** the non-CIME machine config; the 4096-byte namelist buffer (case-name length
  costs bytes); a real Gregorian calendar; `sacct COMPLETED` is not usable output; a partially
  covered scoring window is an error, not a smaller sample.
- **Modes:** `any` — EcoSIM-specific, no FATES dependency.

### `pflotran-run-workflow`
- **Purpose:** The PFLOTRAN (deck-driven) counterpart to `ecosim-run-workflow` — design a probe or
  ensemble, write perturbed input decks, assemble case directories around them, submit, and score
  against `*-mas.dat` columns.
- **Invoke when:** "run a PFLOTRAN experiment/probe/ensemble", "set up PFLOTRAN cases", "submit the
  PFLOTRAN array", "why did my PFLOTRAN cases fail", "score the PFLOTRAN run".
- **Key discipline:** the deck IS the parameter file (cards addressed by block path; the database is
  fixed input, not a calibrated surface); `create_case` assembles around an ALREADY-WRITTEN
  perturbed deck; outputs are `*-mas.dat` columns with no NetCDF history tape; the 806-hour
  observation offset, already applied in `targets.yaml`; an aggregate score can hide a per-species
  inversion; the V0 gate covers time-mean targets on the base case only.
- **Modes:** `any` — PFLOTRAN-specific, no FATES dependency.

### `ats-run-workflow`
- **Purpose:** The ATS (XML-deck) counterpart to `ecosim-run-workflow` — write perturbed Teuchos
  ParameterList decks, assemble cases, submit, and score against the deck's own observation `.dat`
  files.
- **Invoke when:** "run an ATS experiment/probe/ensemble", "set up ATS cases", "submit the ATS
  array", "why did my ATS cases fail", "score the ATS run".
- **Key discipline:** parameters are leaves addressed by PATH through a nested ParameterList; targets
  are **injected into the deck's `observations` block**, not declared as history flags, and an
  observation is already reduced over its region by the deck's `functional`; the `region` grouping
  axis is a string; run ONE case end to end before designing an ensemble, because the adapter's own
  docstring calls the run wiring v0.1.
- **Modes:** `any` — ATS-specific, no FATES dependency.

### `offline-testing-workflow`
- **Purpose:** Design + launch + analyze an offline HPC parameter-sweep experiment on a Morris
  base case — variant matrix, V0 reproducibility gate, dedicated output dirs (config-var paths),
  decision tree → KB injection.
- **Invoke when:** "test the X hypothesis", "parameter sweep", "<param> sensitivity experiment".
- **Modes:** `requires_fates: true` — FATES parameter files + HPC submission.

## Offline phase skills (per-phase, mirror online Phase 0–6)

### `phase0-design`
- **Purpose:** Offline analog of online Phase 0 — sample the parameter space, materialize per-case FATES param files, generate + build + submit the ensemble, arm monitoring.
- **Invoke when:** "design a new round", "submit the ensemble", "sample the parameters", "expand/redesign the parameter space".
- **Modes:** `any` — calibration-workflow phase skill (mode resolved at runtime).

### `phase1-exploration`
- **Purpose:** Offline analog of Phase 1 — extract the Y matrix, run Morris sensitivity, interpret μ*.
- **Invoke when:** "run the sensitivity analysis", "which parameters matter", "run Phase 1".
- **Modes:** `any`.

### `phase2-screening`
- **Purpose:** Offline analog of Phase 2 — rank the ensemble vs targets, find best/most-targets cases, read bias patterns, route to Phase 3.
- **Invoke when:** "screen the ensemble", "which case is best", "how many targets met", "run Phase 2".
- **Modes:** `any`.

### `phase3-diagnosis`
- **Purpose:** Offline analog of Phase 3 (`reasoning.diagnose`) — root-cause the failing targets via the phase3 tools + RAG + Adaptive Memory → structured diagnosis; hand off to Phase 4.
- **Invoke when:** "diagnose the failing targets", "why aren't the targets calibrating", "run Phase 3".
- **Modes:** `any`.

### `phase4-hypothesis`
- **Purpose:** Offline analog of Phase 4 — turn a diagnosis into testable hypotheses + skip-test against existing Morris data (3↔4, no HPC); route to Phase 5 if new sims needed.
- **Invoke when:** "generate a hypothesis", "what should we test next", "can we test with existing data", "run Phase 4".
- **Modes:** `any`.

### `phase5-testing`
- **Purpose:** Offline analog of Phase 5 — thin router to `offline-testing-workflow` for HPC experiment execution.
- **Invoke when:** "run the experiment", "submit the test cases", "run Phase 5".
- **Modes:** `any`.

### `phase6-refinement`
- **Purpose:** Offline analog of Phase 6 — evaluate results vs baseline/expected, extract lessons, update Adaptive Memory, decide converge / rethink (6→3) / redesign (6→0).
- **Invoke when:** "evaluate the results", "what did we learn", "converge or iterate", "run Phase 6".
- **Modes:** `any`.

## Model development (ELM/FATES source-code changes — `requires_fates: true`)

Skills for modifying the **ELM/FATES model source** (Fortran), not just its parameters. Model-evolution on the
pinned checkout, governed by the reproducibility contract (`E3SM_FATES_api43/CLAUDE.md` §1): experiment
branch, **push only to the `jingtao-lbl` fork (never upstream)**, switch-gated default-off, V0-at-equality.

### `model-evolution`
- **Purpose:** The general workflow for evolving **any onboarded model's** *source* — ELM/FATES, EcoSIM, PFLOTRAN, ATS — (mechanism fix, structural refactor, debug instrumentation, new parameter): branch-by-intent, mechanism-first gate, scope-from-source, **preserve the baseline binary before building the change**, switch-gate default-off, paired ON/OFF V0-at-equality verify, log both streams, fork-only push. Umbrella that `add-fates-parameter` routes up to for the FATES knob case.
- **Invoke when:** "update/change the model code", "modify the FATES/ELM/EcoSIM/PFLOTRAN source", "add a mechanism/fix to the model", "promote a hardcoded constant to an input parameter", "refactor the phenology/allocation code", "instrument the model". NOT parameter-file tuning (that's calibration).
- **Modes:** `requires_fates: false` (covers any onboarded model's source); model-dev.
- **Per-model, not generic:** the *workflow* is shared; the **build system** (CIME builds per case, a shared CMake tree has one mutable binary), the **knob surface** (`EDParamsMod`/`EDPftvarcon` vs a guarded NetCDF read path), and the **fork remotes** differ by model.

### `add-fates-parameter`
- **Purpose:** Wire a new FATES parameter (an `EDParamsMod` entry read from the parameter file) into the model source — declare/register/retrieve in `EDParamsMod`, `use` it in the consuming module, and add the value to every parameter file (JSON on api-43, `.nc` on api-31/demo). A **per-PFT** knob goes in `EDPftvarcon`, not `EDParamsMod`.
- **Invoke when:** "add a FATES parameter", "make X an EDParamsMod parameter", "promote this hardcoded constant to a FATES parameter", "switch-gate this model change".
- **Modes:** `requires_fates: true`.
