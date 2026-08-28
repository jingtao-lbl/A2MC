---
name: ecosim-run-workflow
visibility: public
category: calibration
description: Run and test EcoSIM — the non-CIME analog of offline-testing-workflow. Design a probe or ensemble, materialize cases across EcoSIM's THREE parameter-file surfaces, validate before submitting, monitor, and score against the target's own reduce. Use for "run an EcoSIM experiment/probe/ensemble", "set up EcoSIM cases", "submit the EcoSIM array", "why did my EcoSIM cases fail", "score the EcoSIM run", or any EcoSIM Phase-0/Phase-5 work. Encodes the traps that cost real compute — the 4096-byte namelist buffer, the real Gregorian calendar, multi-surface parameter routing, and sacct COMPLETED not meaning usable output.
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

## Step 1 — the three parameter surfaces

EcoSIM cases are built from up to three NetCDF files. Know which is which before editing anything:

| Surface | Env var | Treatment |
|---|---|---|
| primary | `A2MC_BASE_PARAM_FILE` | plant traits — perturbed per case |
| secondary | `A2MC_SECONDARY_PARAM_FILE` | management (e.g. planting density) — **staged FIXED, never edited** |
| tertiary | `A2MC_BASE_PARAM_FILE_3` | `MicrobePars.nc` microbial kinetics — perturbed per case |

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
tape. Census the years before trusting anything:

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

## Changelog

- 2026-08-26: **The two-step source order is now optional, and this file says so.** v2.306 gave every shipped site config a guard that auto-sources its own machine config (`a2mc_config.sh` for CIME/ELM-FATES, `a2mc_noncime_config.sh` for the adapter models) when one is not already loaded, and REPAIRS the wrong one if it was sourced by mistake. Nothing here was wrong -- the explicit machine-then-site order still works and still takes precedence -- so the instruction is shortened and the old form kept as a stated no-op. Asserted by `tests/test_site_config_autosource.py`. PI-directed. Step 0 drops from three commands to one, and its `a2mc_config.sh`-is-the-wrong-file warning changes character: the guard now repairs that choice rather than leaving it to bite. The footgun list says what repair does NOT do -- the ~45 ELM-FATES variables the CIME config left in the shell stay there, so a high `env | grep -c '^A2MC_'` still means start a fresh shell.

- 2026-08-23 (corrected same day): the rule is **PHASE 5 ONLY**; Phase 0 is exempt because its ensemble scripts are config-generated and number in the tens of thousands (PI).
- 2026-08-23: **Phase 5 archives its JOB SCRIPTS into `phase_results/{stem}/submit_scripts/`.** PI-directed. Copy, never move: the scheduler reads the operative copy from the run directory, but that directory is untracked scratch and gets cleaned, while the submit script is where the binary a run was bound to and its run-time hash assertion are written down. A log claiming a passed V0 gate with no archived submit script cannot show which executable produced the number. Signal: on 2026-08-23 a cycle nearly ran against the wrong binary because the materializer emits the LIVE build path by default. Updates `feedback_plot_scripts_canonical_in_phase_results`, which had said run drivers simply stay in CFS.

- 2026-08-22 (later): **The figure script is copied from the case template and adapted.** PI-directed; canonical script stays in `phase_results/{stem}/`, canonical script TEMPLATE in `use_cases/{Model}_{Case}/scripts/`. Part of the three-tier script rule (`calibration-discipline` item 2b).

- 2026-08-22: **Added Step 7, the Phase-6 figure this model owns.** `phase6-refinement` Step 1b calls the sim-vs-obs time series REQUIRED but described it only through the FATES driver, which cannot run on these tapes; nothing on this side claimed the requirement, so it fell between the two skills and this model's experiment cycles produced no such figure at all. Names what the figure must carry (one panel per SCORED target, measurements drawn as measured with gaps left as gaps, control on top, full trajectory), the two reusable pieces here (`control_observations()` for the observed series, `evaluate_model_case` per year for the simulated one so the figure cannot disagree with the score), the leap-calendar rule, and the canonical-script location. Signal: PI, on a cycle report whose only figure showed one of three scored targets against a flat line at the multi-year observed mean. Paired with the `phase6-refinement` and `write-report` edits of the same day.

- 2026-08-18: Initial version — distilled from the EcoSIM BioCON R1-R3 arc, and specifically from the
  R3 design session where the 4096-byte namelist buffer aborted materialization at case 100, the
  deprecated SALib sampler made `--seed` inert, the validator crashed on a scalar parameter in the
  baseline case, and two truncated runs corrupted a probe's gate. Sources:
  `memory/dev_logs_adapterkit/20260818a`, `20260818e`, `use_cases/EcoSIM_BioCON/reports/20260818a_R3_Parameter_Decisions/`.