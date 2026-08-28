# `memory/phase_results/` — the self-documenting artifact folders

**A phase-results folder shares its stem with the phase log in `memory/logs/`.** The log carries the *analysis*; this folder carries the *evidence*, and it must be readable without the companion log.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| the phase producing these artifacts | `phase0-design` … `phase6-refinement` |
| **any figure, before the first `savefig`** | **`plotting`** |
| pairing the folder with its log | **`calibration-log`** |
| running or submitting | `ats-run-workflow` |
| a model-source change | **`model-evolution`** (its record goes to `memory/model_evolution/`, not here) |
| a set that crashed mid-run | **`restart-adapter-ensemble`** |
| the records from the armed monitors | **`arm-hpc-monitoring`** |

## What a complete stem folder contains

For **each** figure, four things — a lone PNG is under-documented:

1. **the figure** (`.png`)
2. **a caption `.md`** — what it shows, how to read it, and its provenance: which script, from what data
3. **the generating `.py`**, saved here — copied from `../../scripts/` and adapted, never a bash heredoc that vanishes
4. **the underlying data** (`.json` / `.csv` / `.txt`)

Plus, where they apply: **`submit_scripts/`** (Phase 5 only — copy, never move; it is the only record of which binary the run was bound to), the cycle's experiment config, `jobs.tsv` and the watcher state, and a **`NOTES.md`** describing and explaining the folder.

## Rules with teeth

- **The stem is canonical.** Never mint a separate letter for artifacts; reuse the log's stem exactly.
- **A dead `phase_results/<stem>/` pointer is an ERROR**, at any age — a citation that resolves to nothing sends a reader chasing it.
- **A figure here that the log does not embed is a WARNING.**
- **Census before scoring.** `sacct COMPLETED` is not evidence of usable output: a case can exit 0 having written a truncated record, or abort while the scheduler reports success. **A crash is not a dead stand** — score neither.

## Reading a stem folder you did not write

Start with `NOTES.md` or the `*_FINDING.md` if there is one, then the caption beside each figure. Every script here is runnable as-is after sourcing the config chain.
