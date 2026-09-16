---
name: ecosim-run-workflow
visibility: public
category: calibration
description: Run and test EcoSIM — the non-CIME analog of offline-testing-workflow. Design a probe or ensemble, materialize cases across EcoSIM's FOUR parameter-file surfaces (plant, management, microbial, soil/grid), validate before submitting, monitor, and score against the target's own reduce. Use for "run an EcoSIM experiment/probe/ensemble", "set up EcoSIM cases", "submit the EcoSIM array", "why did my EcoSIM cases fail", "score the EcoSIM run", or any EcoSIM Phase-0/Phase-5 work. Encodes the traps that cost real compute — the 4096-byte namelist buffer, the real Gregorian calendar, multi-surface parameter routing, and sacct COMPLETED not meaning usable output.
allowed-tools: [Read, Glob, Grep, Write, Edit, Bash]
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [ecosim, hpc]
  summary: "Run/test EcoSIM: multi-surface cases, pre-submission validation, target-driven scoring."
---

# ecosim-run-workflow — run and test EcoSIM

The EcoSIM counterpart to `offline-testing-workflow` (which is FATES/CIME and does not apply here).
EcoSIM is a **standalone binary**: no CIME, no `create_case.sh`, no chained ADSP→RGSP→TRANS legs.
One case is one directory holding its own parameter files, `runfile.nml` and `submit.sh`, and an
ensemble is a SLURM job array over those directories.

Everything below is a trap that has already cost compute or corrupted a result at least once. The
citations are the evidence, not decoration.

## Step 0 — source the RIGHT configs, in order

```bash
source use_cases/<Site>/config/<site>_config_r<N>.sh   # the ROUND wrapper if one exists, else the site config
```

> **If an AGENT is running this, join the `source` to the command that needs it** — `source … && <command>`. A harness gives each shell call a fresh process, so a config sourced on its own is gone by the next call, and the script then reports its variables unset as though nothing had been sourced. A human at a terminal is unaffected. Full statement: `AGENTS.md` §"Source the config and run in the SAME command".


**ONE command since v2.306.** The round wrapper sources the site config, and the site config
auto-sources `a2mc_noncime_config.sh` when it is not already loaded — so the machine config's three
loop limits arrive without you choosing a file. If you sourced `a2mc_config.sh` (the CIME/FATES one,
the wrong file here) by mistake, the guard **repairs** it rather than accepting it
([[feedback_two_machine_configs_cime_vs_noncime]]); it cannot unset the ~45 ELM-FATES variables that
file left behind, so `env | grep -c '^A2MC_'` well above the clean count means start a fresh shell.

The explicit `source a2mc_noncime_config.sh` first still works and is a no-op. Whichever form you
use, **the round wrapper comes last**: it overrides the site config's ensemble name, base files and
targets.

**Footgun.** A round wrapper exports `A2MC_CASE_NAME_PATTERN` for ITS ensemble. Probe-specific
scripts default to `os.environ.get("A2MC_CASE_NAME_PATTERN", "<probe>_{N}")`, so sourcing the round
config silently repoints them at the wrong directory and every case reports `FileNotFoundError` —
which reads as "the array never ran". **Pass `--case-pattern` explicitly to any probe-era script.**

## Step 0b — the EcoSIM knowledge base, BEFORE the source

**`docs/ecosim-knowledge-base/` exists and this skill never mentioned it until 2026-09-05**, which
is why a session spent several turns reconstructing the `micresb` slot semantics from Fortran that
`microbial_bgc/index.md:133` states in one line with the same `MicBGCPars.F90:178-179` citation --
and which additionally records that the 2-slot NECROMASS axis (`micresb`: kinetic, recalcitrant, the
one `SPORC`/`SPOMC` index) is NOT the 3-slot LIVING-biomass axis (`ibiom_kinetic/struct/reserve`).
That distinction is invisible in either declaration read alone, and it mattered.

```bash
git grep -i "<term>" -- docs/ecosim-knowledge-base/      # works with no RAG profile active
```

**KB first, then CONFIRM IN THE SOURCE.** Going to the Fortran first pays twice and loses the cross-axis context nobody re-derives; stopping at the KB leaves an understanding nothing has checked.

**STAGE MATTERS, AND THIS IS THE CALIBRATION-STAGE RULE (PI, 2026-09-06).** While ONBOARDING a model the KB does not exist yet, source is the only recourse, and [[feedback_param_description_can_lie_verify_in_source]] governs: trace the read, then the internal variable, then its usage, especially before setting a bound. **At CALIBRATION stage the case is set up and the KB is assumed well-built, so the KB is where you START and it usually hands you the citation. It does NOT replace verifying in source: a KB page tells you what a thing IS, and only the code settles what it DOES -- or, just as often, what is ABSENT from it, which no page can state.** Query all five surfaces FIRST, then confirm in source. If you are in the source to LEARN what a parameter does rather than to CONFIRM what the KB told you, stop and name which it is: either you skipped the KB, or the KB has a gap. **A gap is a BUILD TASK** (rebuild the wiki, extend the curated seed, curate the round's findings at round close) and not something to route around every cycle.

**THE KB IS FIVE SURFACES, NOT ONE, AND THEY ARE NOT INTERCHANGEABLE. QUERY ALL FIVE, not the first one or two that answer.** They are: the **codebase wiki** `docs/<model>-knowledge-base/<model>-codebase-wiki-<commit>/` (`git grep -i <term> -- docs/<model>-knowledge-base/`, which works with no RAG profile active), the **RAG vector index** `rag/chroma_db/<profile>/` and the **knowledge graph** `rag/graphs/<profile>.json` (both via `HybridRetriever`), the **MODEL-level adaptive memory** `memory/<model>/gained_knowledge/`, and the **SITE-level adaptive memory** `use_cases/{Model}_{Case}/memory/gained_knowledge/`. The last two are the ones that get forgotten and they are populated: 21 entries for EcoSIM at model level, 28 for one case at site level, on 2026-09-05. Measured the same day on ONE parameter, `SPORC`: the knowledge-graph node carried a one-line description and units but no bounds, no code location and no mention of the two-slot axis, while the codebase wiki carried the slot semantics, the defaults AND the `MicBGCPars.F90` citation. Concluding "the KB does not have it" from the thin surface would have been wrong, so check the surfaces that hold that KIND of knowledge rather than the first one you open.

**The curated overlay lives in DIFFERENT PLACES by model family, and looking in the wrong one reads as "it does not exist".** An adapter model keeps it at `models/<model>/curated_seed.yaml`; only the FATES profiles use `rag/data/curated_relationships_<profile>.yaml`. The active profile's `rag/metadata/<profile>.json` names the file its graph was built from, so read that rather than guessing the path. Measured 2026-09-06: `models/ecosim/curated_seed.yaml` was declared missing on the strength of an `ls rag/data/`, and it is human-authored and is what built the EcoSIM graph.

**MEASURED COST OF QUERYING ONE SURFACE INSTEAD OF FIVE (EcoSIM_TeRaCON R1, seven cycles, 2026-09-06).** The graph stated `parameter:RMOM --controls--> mechanism:Microbial_Maintenance_Respiration --affects--> output:CO2_SEMIS_FLX_col`, the exact variable that case scores as `Fs`, and named 12 parameters for that output where a rank-correlation screen surfaced 4. The curated seed's `RMOM` entry carried the mechanism, the `NitroPars.F90:209` citation, the positive sign, the Morris rank and the `VMXO` coupling. The SITE store listed `RMOM` as an untested rank-1 alternative and recorded `CNRT` as a confirmed lever at +41% `plant_C`. All of it was re-derived from correlations across two cycles. The graph also declares three `depends_on` pairs among nine levers composed in one experiment, which is the documented explanation for a non-additivity that got written up as a discovery.

**THEN GO TO THE SOURCE AND CONFIRM IT. This step is not optional and is not reserved for claims you have already decided are load-bearing.** Confirming is not the same as learning: at calibration stage you arrive at the source already knowing what the KB says, in order to check it, so the read is short and targeted. A long exploratory source read at this stage is the signal described above. The KB tells you what a thing IS; the source tells you what it DOES. Open the `file:line` the KB handed you in the checkout at `$A2MC_MODEL_PATH` and read **the code that USES the value**, not only its declaration or its description string: a `description`, a `long_name` or a `units` field in any of these surfaces can be wrong, which is a standing rule here ([[feedback_param_description_can_lie_verify_in_source]]) and is exactly why the KB read is a starting point rather than an answer. Confirming costs one command -- `git -C "$A2MC_MODEL_PATH" show HEAD:<path> | sed -n '<lo>,<hi>p'` -- against the hours a wrong mechanism costs downstream.

For EcoSIM specifically, the wiki records that the 2-slot NECROMASS axis (`micresb`, kinetic/recalcitrant) is NOT the 3-slot LIVING-biomass axis (`ibiom_kinetic`/`ibiom_struct`/`ibiom_reserve`) -- a distinction a source read alone missed and which decided a root cause on 2026-09-05. `models/ecosim/spec.py` and [[reference_ecosim_parameter_surfaces]] are the third
leg: which SURFACE a name lives on.

## Step 1 — the four parameter surfaces

EcoSIM cases are built from up to **four** NetCDF files. Know which is which before editing anything:

> **The fourth is the grid/soil file** (`grid_file_in`, `A2MC_BASE_PARAM_FILE_4`), wired 2026-09-15. **Its axis is the SOIL LAYER, 1-based**, not a PFT: `PH_5` is layer 5. It is unset by default, so a round samples soil properties only when it says so.

| Surface | Env var | Treatment |
|---|---|---|
| primary | `A2MC_BASE_PARAM_FILE` | plant traits — perturbed per case |
| secondary | `A2MC_SECONDARY_PARAM_FILE` | management (planting density `PPI`, cuts, fertiliser) — **per-case when the param list samples a name on it, staged unperturbed when it does not** |
| tertiary | `A2MC_BASE_PARAM_FILE_3` | `MicrobePars.nc` microbial kinetics — perturbed per case |

> **This row changed on 2026-09-01 and the change is easy to miss.** The secondary surface was
> stageable but **not samplable** — a name on it could be routed nowhere, so a param list carrying
> `PPI` refused rather than perturbing it. It is now written per case exactly as primary and tertiary
> are (`materialize_adapter_ensemble.py`, the `secondary_edits` branch;
> `memory/dev_logs_adapterkit/20260901g`). If you read "staged FIXED, never edited" anywhere, that
> text is stale. The dry-run banner now reports which mode is in force -- `secondary(PER-CASE)` vs
> `secondary(fixed)` -- computed from the routing rather than asserted, so check the banner instead
> of assuming.

> **★ WIRING THE TERTIARY SURFACE FOR A NEW CASE — and why an empty `micpar_file_in` does NOT
> mean "unreachable".** Two things are easy to get wrong here, and both have cost a case a
> deferred soil-BGC calibration.
>
> **(a) The BASE namelist is not what reaches an ensemble case.** `create_case` stages
> `tertiary_param_file` and repoints `micpar_file_in` per case (`models/ecosim/backend.py:277-311`),
> so what matters is `A2MC_BASE_PARAM_FILE_3`. A case can run with an EMPTY `micpar_file_in` in its
> base namelist and still calibrate the microbial surface. Wire the namelist too only for the
> STANDALONE path — a probe or spin-up run that does not go through `create_case`.
>
> **(b) Wiring it is FREE if you build the file from the COMPILED defaults.** With the slot empty
> the reader early-returns (`NitroPars.F90:277`) and the run uses `initNitroPars`' compiled-in
> constants, so the parameters are never absent — just not file-backed, and A2MC perturbs files.
> Pointing at the SHIPPED `MicrobePars.*.nc` therefore MOVES the baseline (it differs from the
> compiled values on a handful of entries) and needs a fresh reference run. A file built from the
> compiled defaults reads back the same numbers, so V0 still reproduces the un-wired configuration
> and the surface becomes calibratable at zero cost.
>
> **Compiled defaults are a property of the BINARY, not the site**, so any case binding the same
> `sha256` can reuse one such file. **Verify, don't assume:** diff the candidate against the shipped
> file — only the known-divergent entries should differ.
>
> Do this at ONBOARDING. Deferring it on the belief that the surface is unreachable is the specific
> failure: one case deferred its soil side for exactly that reason and corrected it later
> (`use_cases/EcoSIM_Lusignan/memory/logs/20260904b_phase0_design_r01_*.md`), and a second repeated
> the error eight days on, at a column where heterotrophic respiration dominates
> (`use_cases/EcoSIM_Kougarok/memory/logs/20260912b_*.md`). It is 12 of the curated seed's 47
> calibratable parameters.

Routing is **derived**, never declared: `route_surfaces()` probes each file's variable names and
raises if a parameter is found in both or neither. A param list may carry an optional `surface`
column, which is cross-checked against that probe and raises on disagreement — documentation, not a
second source of truth.

**Stage the bases into a round-owned directory before a large run.** Reading them out of a previous
round's experiment-cycle dirs is fragile: materialization opens each base **once per case**, and
cycle dirs are exactly what gets cleaned under disk pressure. Copy them, verify byte-identical, and
drop a `PROVENANCE.txt` saying what came from where.

**The `pft` column is overloaded.** For microbial parameters it indexes a non-PFT axis (e.g.
`nactbioms`, whose slots are `kinetic` and `recalcitrant`, `MicBGCPars.F90:179-180`). Declare the
real axis as its own column; do not rename `pft` — see the template's extensible-axis rule.

## Step 2 — the namelist, and its 4096-byte cliff

EcoSIM reads a runfile into a **fixed 4096-byte buffer** (`fileUtil.F90:25`) and aborts at startup.
`backend.create_case` gates on it, so materialization fails loudly rather than the run dying later.

**The case name lives inside the staged paths, so every extra digit costs bytes.** A 3-digit
ensemble can fit while a 5-digit one does not, which is why this stays invisible until the round
that needs it. Measured on one site: `case1` 4092 bytes, `case999` 4098, `case59392` 4104.

Keep the operative namelist comment-thin and put the prose in a sidecar `*.ANNOTATED.md`. Verify the
WORST case before materializing thousands:

```bash
python scripts/materialize_adapter_ensemble.py --start <highest-index> --end <highest-index>
stat -c %s "$A2MC_OUTPUT_DIR/<case>/runfile.nml"        # must be < 4096, with headroom
```

Other namelist facts worth not rediscovering: input paths must be **absolute** (the shipped sample's
relative paths do not resolve from a case dir); `create_case` repoints only `pft_file_in`, by
basename; `hist_nhtfrq` is **per-tape**, so a second hourly tape leaves the daily tape alone.

## Step 3 — sample and materialize

```bash
python scripts/create_adapter_parameter_sample.py          # writes matrix + SALib problem
python scripts/materialize_adapter_ensemble.py --dry-run   # ALWAYS dry-run first
python scripts/materialize_adapter_ensemble.py --baseline --baseline-index 0
```

**Always pass `--baseline`.** It materializes an unperturbed V0 case, which is what a
reproducibility gate compares against. A round whose V0 exists only as a matrix row cannot answer
"does the base still reproduce?" — that gate went unevaluable for a whole cycle once for exactly
this reason.

Sobol sampling uses `SALib.sample.sobol` with a real `seed` and `scramble=True`. Do **not** revert to
`SALib.sample.saltelli`: it is deprecated, has no seed, and its `skip_values` is a sequence offset,
not a seed. The seed is written into the SALib problem file so the design is re-derivable at
analysis time.

### `sobol` and `sobol_seq` are DIFFERENT DESIGNS, and confusing them silently invalidates the analysis

`create_adapter_parameter_sample.py` offers four schemes: `morris`, `sobol`, **`sobol_seq`**, `lhs`.
The two Sobol' entries are not variants of one thing:

| scheme | what it builds | analyze with |
|---|---|---|
| `sobol` | the **Saltelli A/B/AB** design, `N(2P+2)` rows with a required block structure | `SALib.analyze.sobol` |
| `sobol_seq` | the **scrambled Sobol' SEQUENCE** — space-filling, every row independent | **given-data estimators**, `scripts/given_data_sensitivity.py` (Borgonovo delta, `rbd_fast`, `pawn`) |

**The trap: `sobol.analyze()` and `morris.analyze()` do NOT error on a sequence design.** They
consume the rows positionally, read a block structure that is not there, and return indices that
look ordinary and mean nothing. Nothing fails, so nothing warns you.

Two consequences worth holding onto. Saltelli **cannot drop rows** — a hole in an A/B/AB block
damages the block, so a design with a meaningful failure rate needs its unusable-row rate measured
on a cheap prefix first (Sobol' is extensible, so an `N=256` block is a true prefix of `N=1024` and
its rows are reused rather than re-run). A `sobol_seq` design has no such constraint: rows are
independent, so a dead case is simply a missing point.

`A2MC_SAMPLING_SCHEME` in the round config records which one a round used. Read it before choosing
an estimator; do not infer the design from the word "Sobol" in the ensemble name.

## Step 4 — VALIDATE before submitting. Non-negotiable.

```bash
python scripts/validate_adapter_ensemble.py --expect-baseline
```

It checks structure, that each case's NC value equals `float32(matrix[i][j])` on **whichever surface
each parameter belongs to**, that the baseline is unperturbed, that non-calibrated variables were not
touched, that each namelist points at that case's OWN staged files, and the submit script. Budget
roughly 45 minutes for a 60k-case ensemble.

A validator that reads only the primary surface passes while the microbial parameters are silently
unwritten. That is the failure mode this step exists for.

## Step 5 — submit and monitor

**Archive the submit scripts into `phase_results/{stem}/submit_scripts/` as soon as they are final** — copy, not move. The run root is untracked scratch; the submit script is the only record of which BINARY the run was bound to and of its run-time hash assertion, and this workflow's own footgun list is why that matters. One per case plus a representative `runfile.nml`. **Phase 0 is deliberately EXEMPT.** Its job scripts are generated from the machine + round config by the materializer, and an ensemble is thousands of cases (one R3 round is 59,393), so archiving them would be both enormous and redundant: the config plus the generator already reproduces them exactly. Phase 5 is different because its handful of variants are hand-designed and hand-repointed, so nothing else records what actually ran.

### How an ensemble is actually submitted

One SLURM **job array** over the case dirs, via the case's own
`use_cases/<Case>/case_template/submit_ensemble_array.sh`. One array task = one case = one serial
EcoSIM run (`srun -n 1`, `OMP=1`, `--cpus-per-task=2`); parallelism is ACROSS cases, never within
one. Raising `--cpus-per-task` cannot speed up a 1-grid-cell run and multiplies the charge.

```bash
source use_cases/<Case>/config/<site>_config_r<N>.sh
mkdir -p "$A2MC_OUTPUT_DIR/logs"        # SLURM fails a task outright if it cannot open its log
sbatch use_cases/<Case>/case_template/submit_ensemble_array.sh
```

**`shared` enforces `MaxSubmitJobsPU = 5000`, and SLURM counts array TASKS individually.** Measured
ceiling: **4,995 pass `sbatch --test-only`**; 14,849 is rejected outright with
`QOSMaxSubmitJobPerUserLimit`. `MaxArraySize` is 65,000 and is NOT the binding constraint. Check
rather than discover:

```bash
sbatch --test-only --array=0-<LAST> use_cases/<Case>/case_template/submit_ensemble_array.sh
```

Over the cap, split into chunks **aligned on the design's own block stride** (the Saltelli stride
for a `sobol` design) so a partially complete ensemble is still analyzable as whole blocks rather
than fragments. Under it — an ensemble of a few thousand — use one array and skip the chunking
entirely.

**A slow hour in `shared` is not evidence that `shared` cannot serve the ensemble.** On 2026-08-20 a
3.5-hour window measured ~20 cases/hour and projected 31 days; the same array then ramped to its
full 512 concurrent and reprojected to ~6.6 hours, because `shared` backfills small tasks into
slivers of busy nodes, which is what that queue is for. The node task-farm
(`submit_taskfarm_array.sh`, 128 serial cases per exclusive `regular` node) is validated and
remains available, but **per-case `shared` arrays are the default** (PI, 2026-08-20). Reach for the
farm only after hours of measurement, not one sampling window. If you do: request `--qos=regular`,
**never `regular_1`** — `regular_0`/`regular_1` appear in `sacctmgr show qos` and are rejected by
`sbatch` with "Job request does not match any supported policy".

Arm monitoring the moment anything is submitted, on YOUR launches only
([[feedback_monitor_only_own_session_launches]]):

```bash
nohup tools/watch_slurm_array.sh -j <jobid> -n <ntasks> -s <stem>/watch_state.json \
      [-x "<extract-and-plot refresh command>"] > <stem>/watch.log 2>&1 &
python tools/check_watcher_state.py <stem>/watch_state.json     # ALIVE/FINISHED/STALE/DIED
```

**Liveness is the heartbeat, not a shell trap** — SIGKILL cannot be trapped, so a log that stops
growing is indistinguishable from a quiet run. Filter on milestone CROSSINGS, never exact counts:
array tasks finish in bursts and exact-value filters miss most of them.

The concurrency throttle (`%N` in the array directive) is a choice, not a property of the design —
the same ensemble can take a month or a week.

## Step 6 — extract and score against the TARGET's own reduce

**`sacct COMPLETED` does not mean usable output.** A case can exit 0 having written a truncated
tape.

**The signal that means "finished" is the FINAL RESTART, never the h0 tape.** EcoSIM opens its
single h0 tape at INITIALISATION and appends to it, so the tape exists from the first minute of the
run — testing for it scores a wall-clock-killed run as COMPLETE, which is exactly the unusable row
you are trying to detect. A restart set stamped `<final year + 1>-01-01` is written only after the
last simulated year finishes. Derive the year from the case's own `runfile.nml`, never guess it:

```
start_date year + sum over forc_periods triplets of (y1 - y0 + 1) * repeats
  e.g. start_date '20000101000000', forc_periods = 2000, 2022, 1  ->  23 years  ->  r.2023-01-01
```

`repeats` is included, so a recycled spin-up counts correctly. This is what
`EcoSIMBackend.check_case_status` uses (`memory/dev_logs_adapterkit/20260820d`): before that fix a
filesystem census reported COMPLETED=32 against `sacct`'s 12, and
`phases/phase2_screening/screen_ensemble.py` was scoring truncated runs as finished. After it, the
scan agreed with `sacct` exactly.

Census the years before trusting anything:

```bash
python - <<'PY'
import pathlib
R = pathlib.Path("<run root>")
short = [(d.name, n) for d in R.iterdir() if d.is_dir()
         for n in [len(list(d.glob("*.h1.*.nc")))] if n != <expected years>]
print(len(short), short[:10])
PY
```

Two calendar rules that silently corrupt results:

- **EcoSIM runs a REAL Gregorian calendar** — 366 records in a leap year, no no-leap switch. Never
  block a tape with `n // 365`; use `tools.calendar_blocks.year_blocks()`
  ([[reference_ecosim_uses_real_leap_calendar]]).
- **A partially covered scoring window is an ERROR, not a smaller sample.** Early termination is
  caused by instability, so the surviving tail is biased toward the blow-up: two truncated cases once
  returned a flux of ~270 against a normal range of 0.1-8, and failed a whole probe's gate.

Score through the target's own `reduce` and `tape`, never a reimplementation. A target may declare a
sub-daily tape and a daytime window (`growing_season_daytime_mean_abs` on `h1`); computing it any
other way produces a number that disagrees with the score for reasons no reader can see.

**Targets vs prescribed inputs.** Anything the run's initial state is BUILT FROM belongs in
`prescribed_initialization:`, not `targets:` — scoring an input rewards the input. `G14` in
`validate_model_targets.py` raises if a name appears in both.

## Step 7 — the Phase-6 figure this model owns

`phase6-refinement` Step 1b requires a **sim-vs-obs time-series overlay covering every scored target**
before the verdict is written, and routes the implementation to each model family's own procedure.
**For EcoSIM that is here**, because the FATES driver (`tools/extract_and_plot_selected_cases.py`)
imports `extract_monthly_variables_FATES`, sums over SZPF size classes and is `_exp`-gated, so it
cannot run against these tapes. Until 2026-08-22 nothing on this side claimed the requirement, so it
fell between the two skills and an adapter model's cycles produced no such figure at all.

**What the figure must carry** (the model-neutral half, restated so it is actionable here):

- **one panel per scored target**, not one panel for the target the experiment aimed at;
- **the measurements as measured** — per-year points with their spread, and gaps left as gaps;
- the **control** drawn on top, so the V0 gate is visually confirmed rather than asserted;
- the **trajectory** across all run years, not the windowed number alone.

**How to build it here.** There is no single driver; there are two reusable pieces plus one rule.

```python
# 1. the observation series -- reuse, never re-derive. It already handles control-plot selection,
#    the literal string "NaN" in the CSV, and the years with no measurement.
control_observations()   # in the Phase-0 folder's plot_three_targets_obs_window.py

# 2. the simulated series -- through the TARGET'S OWN reducer, one call per year, so the figure
#    cannot disagree with the score for a reason no reader can see.
evaluate_model_case(case, [dict(target, window_years=[y, y])], model="ecosim")
```

and the rule: **year blocking comes from `tools.calendar_blocks.year_blocks`**, never `n // 365` —
EcoSIM runs a real Gregorian calendar, so a fixed 365 slips a day per leap year and walks the annual
peak into the wrong year ([[reference_ecosim_uses_real_leap_calendar]]).

**Where it lives.** Copy the case's template from `use_cases/{Model}_{Case}/scripts/` and adapt it; the adapted script is **canonical in `phase_results/{stem}/`** beside its caption and
data; edit and regenerate it there, and copy only the rendered PNG into a report. A worked example
is the cycle-1 corner overlay, which began as a one-target figure and was extended in place to all
three: `use_cases/EcoSIM_BioCON/memory/phase_results/20260822f_*/plot_corner_overlay.py`.

**Self-check before trusting it.** The windowed mean the figure draws must reproduce the number the
scoring path reports. If it does not, the figure is drawing something other than what the round is
scored on, and it should say so instead of plotting.

## Footguns, collected

- Sourcing `a2mc_config.sh` instead of `a2mc_noncime_config.sh`. Since v2.306 the site config's
  guard repairs this, but the CIME variables it left behind are still in the shell.
- A probe script silently inheriting the round's `A2MC_CASE_NAME_PATTERN`.
- Comments creeping back into the operative namelist until a 5-digit case tips it over 4096.
- `ls -1d $DIR/case*` at ensemble scale: exceeds `ARG_MAX` and reports **0**, which reads exactly
  like data loss. Use `os.scandir`.
- Treating `sacct COMPLETED` as "the science is valid".
- Testing for the **h0 tape** as a completion signal: it exists from the first minute.
- Analyzing a `sobol_seq` design with `sobol.analyze()`: it returns numbers rather than an error.
- Assuming the secondary surface is fixed. It is per-case whenever the param list samples it.
- Submitting more than **4,995** array tasks to `shared`: rejected, not queued.
- `--qos=regular_1`: listed by `sacctmgr`, rejected by `sbatch`. Use `regular`.
- Editing a staged base in place — a new base means a new round directory.
- Stdout volume: EcoSIM can write tens of MB per case. At ensemble scale that dominates disk; trim
  or redirect at source before launching.

## Related skills

- `phase6-refinement` (Step 1b, which routes its figure requirement here), `phase0-design`
  (the round-opening wrapper this sits under), `phase5-testing` (the phase router),
  `calibration-discipline` (the per-cycle definition of done), `arm-hpc-monitoring` (monitoring
  contract), `onboard-model` (adding a model, not running one).
- FATES equivalent: `offline-testing-workflow` — CIME-based, does not transfer.

## Notes

- **Branch fit:** `adapter-kit` and any branch carrying the EcoSIM adapter. Model-specific by design
  ([[feedback_per_model_scripts_not_generic]]): the machinery it drives is generic, the traps are not.

