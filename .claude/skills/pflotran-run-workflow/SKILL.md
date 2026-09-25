---
name: pflotran-run-workflow
description: Run and test PFLOTRAN — the deck-driven counterpart to ecosim-run-workflow. Design a probe or ensemble, write perturbed input decks, assemble case directories, submit, and score against *-mas.dat columns. Use for "run a PFLOTRAN experiment/probe/ensemble", "set up PFLOTRAN cases", "submit the PFLOTRAN array", "why did my PFLOTRAN cases fail", "score the PFLOTRAN run", or any PFLOTRAN Phase-0/Phase-5 work. Encodes the traps that have already cost a result — the 806-hour observation offset, an aggregate score hiding a per-species inversion, and a V0 gate that licenses less than it appears to.
visibility: public
category: calibration
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [pflotran]
  summary: "PFLOTRAN's Phase-0/Phase-5 procedure — deck as parameter file, case assembly, submission, and scoring against *-mas.dat. The non-CIME, non-namelist sibling of ecosim-run-workflow."
---

# pflotran-run-workflow — run and test PFLOTRAN

The PFLOTRAN counterpart to `ecosim-run-workflow`. Neither `offline-testing-workflow` (CIME/FATES) nor `ecosim-run-workflow` (namelist-driven) transfers: PFLOTRAN's **parameter file is its input deck**, its outputs are **`*-mas.dat` columns with no NetCDF history tape**, and a case directory is a deck plus the static files that must sit beside it.

Everything below is either read from `models/pflotran/` or has already cost a result at least once. The citations are the evidence, not decoration.

## Step 0 — source the RIGHT configs

```bash
source use_cases/<Case>/config/<case>_config.sh    # auto-sources a2mc_noncime_config.sh
```

> **If an AGENT is running this, join the `source` to the command that needs it** — `source … && <command>`. A harness gives each shell call a fresh process, so a config sourced on its own is gone by the next call, and the script then reports its variables unset as though nothing had been sourced. A human at a terminal is unaffected. Full statement: `AGENTS.md` §"Source the config and run in the SAME command".


**`a2mc_config.sh` is the CIME/FATES one and is the wrong file here** ([[feedback_two_machine_configs_cime_vs_noncime]]). Since v2.306 the site config loads the right machine config itself and repairs a wrong choice, so one command is the whole chain — but it cannot *unset* the ~45 ELM-FATES variables a mistaken `a2mc_config.sh` left behind. A variable count well above the case's clean one means start a fresh shell.

## Step 1 — the parameter surface is the DECK, and there is only one

| surface | file | status |
|---|---|---|
| primary | `pflotran.in` — cards addressed by **block path** | perturbed per case |
| database | `savannah_river.dat` — thermodynamic Keq/stoichiometry | **fixed input, NOT calibrated** |

`write_parameter_file` raises `NotImplementedError` for `surface="database"`, and the reason is a decision, not a gap: the database has **no calibration knob in the current parameter list**, whose own EXCLUDED section says "the DATABASE is fixed input". Adding one is a design change, not a flag.

**A parameter is a card, addressed by block path**, and its canonical id is `{name}_{group}` per the param list's own convention — `RATE_CONSTANT_Glass_FB`, `M_all3`, `PERM_ISO_Bolitic`. The grouping axis is **`region`**, a *string* axis: a tool that coerces the axis to an int raises on this list.

**Where the docs and the source disagree on a card name, the SOURCE name wins.** That rule was established by a 95% agreement audit of the mined registry (314/329) which turned up two upstream doc typos. Some cards are also **`writable: False`**; a parameter list naming one produces a case that silently ignores it.

**Bounds are `provisional:` by construction** unless refined — the seed was default-anchored, not literature-derived. Say so in `bound_source`; do not imply a provenance the row does not have.

## Step 2 — write decks, then assemble cases (the calling convention matters)

The order is **not** the one you would guess. `write_parameter_file` writes the **perturbed deck directly at its final location**, and `create_case` then assembles the directory *around a deck that already exists*:

> `param_file` is not a template to copy — it is the PERTURBED deck, already written by `write_parameter_file` at `run_root/case_name/<deck name>`. This method's job is narrower: stage the static, per-round-constant files beside it.

So `create_case` needs `config["A2MC_BASE_PARAM_FILE"]`, which names the **base case directory** where the mesh, restart, rainfall and database live. It raises `KeyError` without it. A case that stages the deck and forgets the database is not the case you designed.

`secondary_param_file` raises `NotImplementedError` — there is no second calibrated surface yet.

## Step 3 — validate before submitting

```bash
python scripts/validate_adapter_ensemble.py --expect-baseline
```

**Always materialize a `--baseline` case.** A round whose V0 exists only as a matrix row cannot answer "does the base still reproduce?", and that gate went unevaluable for a whole cycle on another model for exactly this reason.

## Step 4 — submit and monitor

`submit_ensemble` sbatches each case's `submit.sh`, writes `job_id.txt` beside it, and returns synthetic `DRYRUN-*` ids when `A2MC_DRY_RUN` is truthy **or `sbatch` is not on PATH** — so a dry run on a login node without SLURM looks identical to a real submission unless you check the ids.

Arm monitoring the moment anything is submitted, on **your own** launches only ([[feedback_monitor_only_own_session_launches]]) — follow `arm-hpc-monitoring`; do not re-derive a watcher shape.

**Rank count is an ensemble-design decision, and it perturbs the solve.** Measured 2026-08-07 over the first 8 timesteps against the team's reference run, which was **serial**:

| | bit-identical values | worst relative difference |
|---|---|---|
| serial | **70.75%** | 3.2e-4 |
| 8 ranks | 68.49% | 5.6e-4 |

Serial is also the cheaper ensemble shape: the run needs 32 MB and about one core-hour, so roughly 128 members pack onto one node instead of one member per node. `A2MC_HPC_MPI_RANKS` is set **unconditionally** in the site config for exactly this reason — a `${VAR:-N}` fallback there would never fire, since the machine config already set it ([[feedback_layered_config_override_must_be_unconditional]]).

## Step 5 — status, and what "done" actually means

`check_case_status` returns `PENDING` | `RUNNING` | `COMPLETED` | `FAILED`, keyed on the case's `.out` file and **`PFLOTRAN_EXIT_FAILURE = 88`**.

**A scheduler-COMPLETED case is not a usable case.** Census the outputs before trusting anything: `extract_history_variables` raises `FileNotFoundError` if no `*-mas.dat` is under the case path, and a truncated `-mas.dat` is a smaller sample only if the run ended for a benign reason — early termination is usually instability, so the surviving tail is biased.

## Step 6 — score against the target's own reduce

`parse_outputs` inventories a `*-mas.dat` **header** — "there is no output CDL for this model." Outputs are mass-balance columns plus Tecplot snapshots; there is **no NetCDF history tape**, so nothing here resembles the FATES or EcoSIM extraction path.

Three findings that have already changed a result:

1. **The observation window carries an 806-hour offset.** Measured hour 0 is MODEL hour 806, source-verified against the team's own `Figures/update_remaining_figures.py:31`. A window written as `[0, 768]` in model time contains **zero** observations and **does** contain spin-up. miniLEO's `targets.yaml` already applies the offset (`window: [806, 1574]`) — **do not apply it twice.**
2. **An aggregate score can hide a factor-of-two per-species error.** Correcting that window moved the mean `|1 − ratio|` by 0.184 → 0.180 while **Mn inverted**, from 19% over to 39% under. That is why the error survived review, and it generalises to any campaign scoring several targets into one aggregate. **Report per-species beside the aggregate.**
3. **The V0 gate licenses less than it appears to.** It passed for **time-mean targets only**, on the **base case only**, and is **toolchain-specific**: it was run for the `cpe/23.12` build, a rebuild on a new Cray PE has to re-run it rather than inherit it (the `cpe/25.09` rebuild's re-run is recorded in `models/pflotran/BUILD.md`). It does not license point-wise or peak-timing scoring.

## Step 7 — the Phase-6 figure this model owns

`phase6-refinement` step 1b requires a sim-vs-obs overlay **covering every scored target** before the verdict is written, and routes the implementation to each model family. For PFLOTRAN that is here.

The figure must carry: **one panel per scored target**, not just the one the experiment aimed at; the **measurements as measured**, with gaps left as gaps; the **control drawn on top** so the V0 gate is visually confirmed rather than asserted; and the **whole trajectory**, not the windowed number alone.

Score through the target's own `reduce` (`outflow_concentration`, `outflow_flux`) rather than a reimplementation, or the figure and the round's score disagree for a reason no reader can see. Copy the case's template from `use_cases/{Model}_{Case}/scripts/` and adapt it; the adapted script is **canonical in `phase_results/{stem}/`**, beside its caption and data.

## Model source, if it comes to that

The PFLOTRAN source and docs are **separate Bitbucket repos**; the GitHub mirror is dead. The private mirror is the `fork` remote and `origin` push is **disabled** — push model source to `fork`, never upstream ([[reference_pflotran_repos_and_clones]]). PFLOTRAN builds into a **shared CMake tree**, so `model-evolution` step 3.5 applies in full: archive the binary *before* building the change, record it with `tools/binary_archive_manifest.py --generate`, and bind runs to the archive rather than the live path.

`petsc-3.24` has been **tested and fails** on our pin, so a retired Cray PE is met by rebuilding PETSc 3.21.4 on a current one, not by moving to a newer PETSc. `cpe/23.12` was retired in 2026-09 and the current build is on `cpe/25.09`; getting and building it is `models/pflotran/BUILD.md`.

## Footguns, collected

- Sourcing `a2mc_config.sh` instead of letting the site config chain the non-CIME one.
- Treating `create_case` as "copy a template deck" — it assembles *around* an already-written perturbed deck.
- Forgetting the database, mesh or restart files beside the deck.
- Reading `DRYRUN-*` job ids as a real submission, or a missing `sbatch` as a failure.
- Scoring a window in raw model time without the 806-hour offset — or applying it twice.
- Reporting only the aggregate, which can move 0.004 while a species inverts.
- Reading the V0 pass as licensing point-wise or peak-timing scoring.
- Assuming a card name from the docs when the source spells it differently.

## Related skills

- `phase0-design` (round opening), `phase5-testing` (the phase router), `phase6-refinement` (step 1b routes its figure requirement here), `restart-adapter-ensemble` (recovering a failed set), `arm-hpc-monitoring`, `calibration-discipline`, `plotting`, `model-evolution`, `onboard-model`.
- Siblings that do **not** transfer: `ecosim-run-workflow` (namelist-driven), `offline-testing-workflow` (CIME/FATES).

## Notes

- **Branch fit:** `adapter-kit` and any branch carrying the PFLOTRAN adapter. Model-specific by design ([[feedback_per_model_scripts_not_generic]]): the machinery it drives is generic, the traps are not.

