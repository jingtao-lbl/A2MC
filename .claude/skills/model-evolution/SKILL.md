---
name: model-evolution
visibility: public
category: model-dev
description: The general workflow for evolving a MODEL'S SOURCE — ELM/FATES, EcoSIM, PFLOTRAN, ATS or any onboarded model — for an algorithm/mechanism fix, a structural refactor, debug instrumentation, or a new parameter. Use when changing model code, not calibration params — "update the model code", "change/modify the FATES/ELM/EcoSIM/PFLOTRAN source", "add a mechanism/fix to the model", "promote a hardcoded constant to an input parameter", "make a structural model change", "refactor the phenology/allocation code", "instrument the model". Umbrella that `add-fates-parameter` (the FATES add-a-tunable-knob sub-recipe) routes up to. NOT for parameter-file tuning (that's calibration).
allowed-tools: [Read, Glob, Grep, Write, Edit, Bash]
modes:
  requires_fates: false      # covers ELM and/or FATES source; model-dev, not a calibration phase
  nutrient_pathway: any
  scope: [model-dev]
  summary: "The disciplined workflow for changing ELM/FATES source — branch, default-off, paired verify, log both streams, fork-only push."
---

# model-evolution — evolving a model's SOURCE under the reproducibility discipline

*Changing model code* is not like editing a parameter file — it's a disciplined workflow so the change is
isolated, switch-gated, verified equal-to-baseline when off, logged where the public can see it, and pushed
only to the personal fork. This skill is that workflow; `add-fates-parameter` is the specialized sub-recipe
for the FATES "add a tunable knob" case. Read the model-tree contract first: the model checkout's
`CLAUDE.md` §1 (paths recorded in [[feedback_model_source_push_fork_only]]).

**Applies to EVERY onboarded model, not only ELM/FATES.** The *workflow* is generic — branch, preserve the
baseline, switch-gate default-off, paired verify, log both streams, push fork-only. What is per-model is the
**artifact handling**: the build system (step 3.5), where a tunable knob lives (step 3), and the fork
remotes (step 7). FATES supplies most worked examples below because it has the longest history here; EcoSIM
([[reference_ecosim_fork_and_anchor]]) and PFLOTRAN ([[reference_pflotran_repos_and_clones]]) follow the
same steps with their own checkouts and fork remotes, recorded in those memories rather than here. The
FATES anchor is main's api-43-1 (E3SM `d40b843` / FATES `e027a40`).

> **Decision — is this even a model-code change?** Tuning a value in a parameter file = **calibration**
> (Phase 0/5, not this skill). Changing *what the code does* (a mechanism, a loop, a cap, a new
> parameter's wiring) = **model evolution** = this skill. If the change is purely "add a new tunable/
> switchable knob," this skill's step 3 routes you into **`add-fates-parameter`** for the plumbing.

## The workflow (each step is a gate the next depends on)

**0. Branch by intent (not dogma).** A **small change you intend to keep** in the working model can go on
the working branch (`fork/master` for E3SM, `fork/main` for FATES). Use a **dedicated experiment branch**
cut from the anchor for **exploratory / A-B / reproducibility-sensitive** work — there, keep the pinned
baseline rebuildable and never edit the anchor in place. (Contract: `E3SM_FATES_api43/CLAUDE.md` §1a. This
is main's working-model policy; the frozen manuscript branch (demo/api-31) is stricter — always an
experiment branch.)

**1. Mechanism-first — GATE the build on evidence, don't assume.** *Wiring is easy; the control point is
where it fails.* Before paying for a structural change, verify **on existing data (cheap, no HPC)** that
the mechanism can actually move the target.
- Positive precedent (demo #17 `phen_gddthresh_c`): a partial-dependence analysis showed PFT9-leaf and
  PFT10-fineroot want *different* values of the shared parameter → decoupling it per-PFT is justified. The
  gate PASSED *before* any code was written.
- Negative precedent (demo #16 `max_plant_density`): Options A (per-event cap) and B (crown-area) were
  wired perfectly and **still failed** — wrong quantity controlled; only C (count-based) worked, found by
  **instrumentation** (debug dumps). When the right control point is unclear, **instrument first**
  (temporary debug output), analyze, *then* implement.
- Do not escalate to model-dev on an unverified assumption ([[feedback_performance_experiment_is_the_objective]]
  — earn model-dev only after the calibration loop is provably exhausted).

**2. Scope from source, THEN implement (comment `!Jing Tao:`).** *The real scope is routinely bigger than
the sketch — read before you write.* (demo #17: the "redimension a scalar + a phenology tweak" sketch was,
in the source, a ~6-file refactor + a restart-format change.)
- **Map the subsystem from the CODEBASE WIKI first — in-repo, free, and no traversal at all.**
  `docs/<model>-knowledge-base/<model>-codebase-wiki-<commit>/` carries `file:line` citations for the
  register/retrieve paths, state couplings and module layout, so
  `git grep -n '<symbol>' -- 'docs/<model>-knowledge-base/'` answers "which files hold this, and how
  does it work" without reading the checkout. This is the cheap step that makes the next one small: a
  consumer census scoped to files you already know matter, instead of a blind sweep. It is what root
  `CLAUDE.md` rule 7 already requires (knowledge base before assumption), and on a shared filesystem it
  is the difference between a compliant search and a prohibited one
  ([[feedback_nersc_no_recursive_traversal]]). When you don't yet know the symbol's name, enter through
  RAG (`HybridRetriever.get_targeted_context()`).
  **Check the pin before trusting a line number** — `git -C "$A2MC_MODEL_PATH" rev-parse --short HEAD`
  (and the submodule's own HEAD) against the wiki directory's commit suffix. Drifted is the *normal*
  state mid-experiment. The wiki's **file names and symbols still hold**; its **line numbers may not**.
  Tier the damage rather than distrusting the whole wiki, and note that "page cites a changed file" is
  the WRONG filter — core modules are cited nearly everywhere (measured 2026-08-14: **55 of 56** FATES
  pages). Compare `git diff -U0 <pin>..HEAD` hunk ranges against each page's own `File.F90:NNN`
  citations:
  | Citation lands… | Meaning | Action |
  |---|---|---|
  | **inside** a changed hunk | content may be wrong | re-verify, or regenerate that page (**6** pages) |
  | only **after** a hunk | content intact, line shifted | tolerate; re-anchor if it matters (43 pages) |
  | neither | untouched | nothing |
  **Refresh the wiki when your change LANDS, not when upstream cuts a release** (PI, 2026-08-14).
  While you are still on the experiment branch, just re-verify the handful of tier-1 pages with
  `git grep` — the branch may yet be reworked or abandoned, so pinning a wiki to it is churn. Once it
  has passed paired verification (step 5) and merged to the fork's `main`, the change is permanent in
  the tree `A2MC_MODEL_PATH` resolves to, and the wiki is now wrong about the model you actually run:
  that is the moment for `generate-codebase-wiki` **Workflow C** (targeted drift refresh). Do not wait
  for an api-epoch milestone — those are rare and expensive in FATES, so milestone-gating would leave
  the wiki stale for months against a model that has moved.
- **THEN grep EVERY consumer** of the symbol/state — now scoped by the files the wiki named, not the
  whole tree. Removing or redimensioning a variable
  breaks every reader you miss — a compile error at best, a silent wrong-answer at worst. (demo #17:
  `ED_val_phen_c` had one consumer; the *state* it feeds, `%cstatus`, had 15.) **Pick the tool from the
  filesystem the checkout is on:**
  ```bash
  # Personal workstation (local clone) — a filesystem walk is fine, and it sees submodules:
  grep -rn '<symbol>' --include='*.F90' "$A2MC_MODEL_PATH"

  # Shared HPC filesystem (NERSC /global, /pscratch, any site scratch) — recursive traversal is
  # PROHIBITED there ([[feedback_nersc_no_recursive_traversal]]); use the index instead:
  git -C "$A2MC_MODEL_PATH" grep --recurse-submodules -n '<symbol>' -- '*.F90'
  ```
  **If you take the `git grep` branch, `--recurse-submodules` is mandatory.** FATES is a git *submodule* of
  E3SM (`components/elm/src/external_models/fates`), and `git grep` stops at the submodule boundary:
  verified 2026-08-14, `EDPftvarcon` returns **0** files from the E3SM root without the flag and **31** with
  it. `grep -r` never had this problem, because a filesystem walk descends into the submodule directory
  regardless — so the HPC-safe tool is the one needing extra care, not the reverse. A silent zero reads as
  "no consumers" and is exactly the miss this step exists to prevent
  ([[feedback_dont_assert_absence_from_one_grep]]). Note also that `git grep` searches only **tracked**
  files, so an untracked scratch `.F90` in the checkout is invisible to it.
  **This covers the harness's own search tool, not just the shell.** A coding agent's `Grep`/`Glob` tool is
  ripgrep doing a recursive walk, so aiming it at a checkout under `/global`/`/pscratch` is the same
  prohibited operation as typing `grep -r` — reach for `git grep` via Bash there instead. (On a personal
  workstation the tool is fine and is the better ergonomic choice.)
- **Verify the framework mechanism EXISTS — don't assume.** #17's sketch assumed `EDParamsMod` could hold a
  PFT-dimensioned param; the source showed it has no clean array-retrieve, so the param moved to the
  idiomatic per-PFT container `EDPftvarcon`. Read the actual register/retrieve path before choosing where a
  thing lives.
- **MIN vs FULL — a local change can be a bug if the quantity is coupled to global state.** A "minimal"
  local edit that leaves coupled downstream state inconsistent is not a shortcut. (#17: a per-cohort
  leaf-out gate was *not* viable — site-level status drives cohorts through two coupled channels, flush
  trigger + biomass target — so it had to become a full per-PFT state promotion.)
- **Find an existing working TEMPLATE in the same codebase and MIRROR it — don't invent.** #17's per-PFT
  cold-status refactor mirrors the already-working drought-deciduous `dstatus(maxpft)` design. Mirroring a
  proven pattern is far lower-risk than a fresh structural change. Look for the analogue in the **wiki**
  first (it describes subsystems, so an analogous feature is usually named there), then confirm in source
  with the scoped `git grep` above.
- For a genuinely large map, **fan out a read-only subagent** to enumerate consumers + the state coupling +
  the template — point it at the **wiki** as its entry point, and if the checkout is on a shared HPC
  filesystem, state the constraint IN its prompt (`git grep --recurse-submodules` only, no
  `grep -r`/`find`). A subagent runs its own tool loop and inherits neither this rule nor the harness's
  traversal hook if it shells out from a different working directory.

Then implement; every edited/added line gets a detailed `!Jing Tao:` comment — mechanism, units, value
choice, follow-ups ([[feedback_model_code_comment_jing_tao]]). This is the in-source audit trail.

**3. Switch-gate — DEFAULT-OFF = bit-for-bit baseline.** For a **reproducibility-sensitive or exploratory**
change, make it **default-off**: a no-op value or a switch such that a switch-off build reproduces the
baseline **bit-for-bit** (the *V0-at-equality* gate). If the change is a tunable/switchable knob, promote it
to a **parameter of that model's own input surface** — for FATES, **follow `add-fates-parameter`** for the
declare/register/retrieve + every-param-file wiring (a **scalar/global** knob goes in `EDParamsMod`, a
**per-PFT** knob in `EDPftvarcon`, which has the clean array-retrieve `EDParamsMod` lacks). For a model
whose parameters come from a NetCDF read path (EcoSIM's `MicrobePars.nc`, via `NitroPars::ReadPars`), the
equivalent is a module-level carrier + a **guarded** read, so a file lacking the new variable falls back to
the old hardcoded default instead of aborting — that guard *is* the default-off. Whichever surface: the
default must reproduce the pre-change values exactly, and you should prove it (compare the new default
against the literal it replaces element-for-element, not by eye). (A small keep-it change on the working
branch need not be
switch-gated — but you then can't V0-at-equality it against the anchor; build from the anchor for a clean
baseline.)

**3.5. PRESERVE THE BASELINE BEFORE YOU BUILD THE CHANGE — a branch isolates SOURCE, not ARTIFACTS.**
*Know your build system before step 4, because the two families behave oppositely here.*

| Build system | Where the executable lives | Consequence |
|---|---|---|
| **CIME** (ELM/FATES) | per **case**: each case owns its `bld/` | a baseline case is independent; you can build it later |
| **Shared CMake/make tree** (EcoSIM, PFLOTRAN, ATS) | **ONE** tree, e.g. `build/<config>/bin/<exe>` | **every build overwrites it in place, whatever branch is checked out** |

On a shared tree, **step 4 destroys the baseline** — which means following steps 0-5 in order is *wrong*
for these models unless you preserve first. Before building the change, either **archive the current
binary** keyed `<branch>_<commit>` with its content hash and a `PROVENANCE.txt`, or **build the baseline
first**. Once overwritten, the only recovery is a rebuild, and a rebuild is no longer the artifact that
produced the published results (a recompile can perturb FP; see step 5).

**Archiving is not finished until the manifest records it.** The archives live OUTSIDE git (25 MB
each), so "archived" used to mean nothing was written down that they existed: every SHA256 sat only
in a gitignored `PROVENANCE.txt`, and a deleted or altered archive would be discovered by a run
failing. Record it, then verify:

```bash
python tools/binary_archive_manifest.py --generate --model <model>   # after archiving a new build
python tools/binary_archive_manifest.py --verify                     # M1-M7; exit 0 required
```

`--verify` is what makes the round ledger's provenance claims checkable rather than asserted: **M7**
resolves each round's `archived_build` + `sha256_prefix` in `config/calibration_rounds.yaml` against
the manifest, so a round citing a binary the manifest does not hold, or citing the wrong checksum,
is an ERROR. Run it after archiving, and again at the round close when
`summarize-calibration-round` writes `round_binaries`.

Two rules learned the hard way (2026-08-07, EcoSIM `SPOSC`): **(a)** `git checkout <parent>` carries
UNCOMMITTED changes with you, so commit (or stash) the change before any baseline branch-switch, or you
will build a "baseline" that silently contains it — the confirm-on-parent grep in step 5 is what catches
this. **(b)** Never derive an archive label from the *checked-out branch*: after a guarded baseline build
the tree is restored to one branch while the build dir still holds the other's binary, so branch-derived
labelling mislabels it. Label explicitly.

**(c) Archiving is only half the job — POINT THE RUNS AT THE ARCHIVE.** Preserving the baseline stops
you *losing* an artifact; it does not stop a later rebuild *swapping* the artifact a run resolves. A
queued job resolves its executable at **run** time, and on a shared tree the rebuild need not even be
yours. So **every run whose output you will rely on — both verification arms and the production
ensemble — must name an archived, content-addressed binary, never the live build path.** Make the
launcher *refuse* a live path rather than trusting the caller:

```bash
case "$EXE" in */build/*) echo "ERROR: refusing the LIVE build path" >&2; exit 1;; esac
```

Two silent near-misses on this tree, neither of which produced an error message: a V0 job exec'd
19:53:24 while the shared binary was relinked 19:59:07 (**5m43s** of margin, 2026-08-07), and an
unrelated CIME `case.build` from a different effort starting on the same login node **four minutes**
after a link step (2026-08-21). Full rule + the A2MC-specific exposure (`A2MC_ECOSIM_BINARY` falls
back to the live path): [[feedback_bind_runs_to_archived_binaries]].

**4. Build — verify by ARTIFACT, never by exit status.** Fresh build of the changed source (the code
changed, so the executable must recompile). For a subsequent multi-variant experiment on that build, reuse
it per `offline-testing-workflow` Step 5 (one build serves all param-file variants; `e3sm.exe` is
phase-agnostic).

**Gate it on things the build actually produced** — the executable's mtime, the *changed modules'* object
files, and a zero count of `error:` in the log. An exit status is not evidence: on 2026-08-07 three
consecutive "exit 0"s were all false — `nohup` on a non-executable script (nothing ran at all),
`nohup … &` returning while nine compilers were still going (mid-build), and a wait loop whose `pgrep -f`
pattern **matched its own command line** while the success string it grepped for was printed by the
invoking wrapper rather than the build script, so neither branch could ever fire.

**5. Paired verification — ON vs OFF, before trusting anything.** For a switch-gated change, run it **ON**
(does the intended thing) *and* **OFF** (reproduces baseline) — do not interpret any result until the OFF
run confirms V0-at-equality (build/env/seed drift otherwise masquerades as signal).

> **⚠ V0 CANNOT VALIDATE ITSELF — make the pass criterion a CONJUNCTION.** A V0 pass is "outputs
> identical". But **running the same binary twice also produces identical outputs**, so the check's
> success state is indistinguishable from a specific, plausible harness error
> ([[feedback_a_check_that_cannot_fail]] — in the very gate that certifies a model change as safe).
> Two requirements, both necessary:
> - **Bind each arm to an IMMUTABLE, content-addressed binary** (the archived copies from step 3.5) —
>   never the live build path. This is the general rule of step 3.5(c) applied here, not a V0-only
>   precaution: it governs the production ensemble too ([[feedback_bind_runs_to_archived_binaries]]).
>   A queued job resolves its executable at **run** time, so a rebuild between
>   submit and start silently swaps it. Real near-miss: a V0 job exec'd at 19:53:24 while the shared
>   binary was relinked at 19:59:07 — 5m43s of margin between a valid V0 and a parent-vs-parent run that
>   would have "passed" perfectly.
> - **Record both arms' binary hashes and assert they DIFFER**, as part of the pass. Identical outputs
>   plus provably different executables is evidence; identical outputs alone is not.
- **If the change alters the restart or history I/O layout** (e.g. promoting a scalar to per-PFT changes
  the restart variable's *shape*), the V0-at-equality check **must be a fresh COLD-START chain** (a spin-up
  *is* a cold start), NOT a warm restart across the format boundary — and an old-format restart cannot be
  read across the change. Check whether your edit touches `FatesRestartInterfaceMod` /
  `FatesHistoryInterfaceMod` before planning the verification run.
- **Same-env PAIRED build — never diff against an *old* build.** A recompile can perturb FP
  (`E3SM_FATES_api43/CLAUDE.md` §1), so V0 is only meaningful between the change branch and its **parent
  built in the SAME env/session**. Clean control: `git diff <parent> <change-branch>` = **exactly the
  changed files**, so any output diff is attributable solely to the change. Diff the paired runs' science
  outputs for **exact** equality (`max|A−B| = 0`), excluding variables the change intentionally reshaped.
- **Build the same-env baseline with a GUARDED in-place branch-switch — a submodule worktree does NOT
  compose with CIME** (CIME compiles FATES from the one fixed in-tree path; no per-case source override, so
  a `git worktree add` of the parent is never seen by the build). On a **committed, clean** submodule:
  `git checkout <parent>` in place → build a dedicated baseline case → **always restore** the change branch
  (`trap restore EXIT` + `set -e` + a clean-tree hard-gate + a "confirm-on-parent" grep); verify afterward
  that the branch is restored and the tree clean. Safe because the already-submitted change-branch chain
  reuses its **frozen exe**, not the source.
- **A scalar→per-PFT V0-off param broadcasts the baseline CASE's own value, not the code default.** If the
  promoted parameter is Morris-varied, the test case carries its *own* value — set **all PFTs to that
  scalar** so off = bit-baseline; the code default makes a *different* run, not a V0.
- **The V0 param file must carry EVERY registered param the build's lineage added — derive it from a
  *post-change* file, not the pristine ensemble/default file.** When experiment branches **stack**, the
  executable needs the *union* of all registered params added anywhere in the lineage. A V0 file built from
  the pristine Morris/default file silently drops them and the run **aborts at param read**
  (`check_var: <name> is not on dataset` → `ENDRUN` — a runtime abort, NOT a build error, so it slips past
  the compile gate). Build the V0/test file from the immediately-prior experiment's param file. This bites
  BOTH the OFF and the baseline file. (Worked recipes — `compare_v0.py` / `build_baseline.sh` — and the
  driving failure live on the **demo branch**: #17 phen-split V0 aborting on #16's missing
  `fates_max_plant_density`, demo branch's model-dev logs of 2026-07-09 and 2026-07-10.)

**6. Log it — under the CASE, in one place.** (PI, 2026-08-24: model update logs now live with the case that runs them, so the mechanism and its effect on the calibration are readable together and both ship with the case.)

- **The change itself** — what you altered and why, the mechanism, the `!Jing Tao:` source comment, the V0-at-equality result, the commit and branch — goes in the case's `use_cases/{Model}_{Case}/memory/model_evolution/{stem}.md`, stem `YYYYMMDDx_model_evolution_r{RR}_{descriptor}.md`.
- **Which rounds ran it, and what that means for comparing them**, goes in the same stream's per-round record plus the case's `config/calibration_rounds.yaml` `model_change_ledger` (commit, branch, `kind`, default-off or not, V0 result, `rounds_before` / `rounds_after`). Written at the round close by `summarize-calibration-round`; what this skill owes it is an accurate commit, branch, `kind` and V0 result to copy.
- **Write it to be self-contained.** Define the terms, restate the approach, do not write a pointer and call it a record. Whoever reads it will not have your session.
- **Required sections** (PI, 2026-09-24), each checked:
  - **`## Summary`** — what changed and what it did, in one honest paragraph.
  - **`## Files Changed`** — which source files, with the `!Jing Tao:` annotation named. A record of a source change that does not say which files is missing the part a reviewer acts on.
  - **`## Verification`** — carrying a **`**V0-at-equality:**`** line. **The verdict alone is not evidence:** step 5's pass criterion is a CONJUNCTION, because running the SAME binary twice also produces identical outputs, so "outputs identical" is indistinguishable from a plausible harness error. Put **both arms' binary hashes** in this section and show they DIFFER. If no source was authored — an activation record, a build-provenance record — write `**V0-at-equality:** not applicable — <reason>`; silence is not an escape.
  - **`## Skills and memory invoked`, naming `model-evolution`.** Writing one of these means invoking this skill, so a record that does not claim it was written without the source of truth open — the same reasoning as the dev-log claims check one level down.
  - `## Cross-references` and a commit-like identifier are expected (warnings); the round's `model_change_ledger` copies a commit out of this record.
- **The ledger row is a COPY of this record, and the copy is checked.** `model_log` points at the record; write it **case-relative** (`memory/model_evolution/<stem>.md`) — it is resolved against the case first, then the repo root, so the retired repo-root archive stays expressible. `python3 tools/check_model_change_ledger.py` asserts the pointer resolves to a FILE, that the record carries the row's `commit`, and that every record is named by some row. Pre-commit check (25). The record is the SOURCE; when they disagree, the row is what changed.
- **Check it before committing:** `python3 tools/check_model_evolution_conformance.py <record.md>` (exit 0 clean / 1 warn / 2 error), which the pre-commit hook runs on a staged record as check (24). It is the third sibling beside `check_log_conformance.py` (dev logs) and `check_calibration_log_conformance.py` (calibration logs), and each refuses the others' streams by name rather than mis-checking them — this stream has its own stem and a `**Round:**` header, and deliberately no `Summary`/`Files Changed`/`Verification`. Records dated before 2026-09-24 are exempt and counted, not blocked.

**7. Push — fork only, NEVER upstream.** Push to your **own fork** of the model repo (your fork of
`NGEET/fates` for FATES, of `E3SM-Project/E3SM` for ELM), **never** the upstream repos themselves. On the
model clone the fork is the `fork` remote and `origin`'s push URL is a `DISABLE`d sentinel — so
`git push fork <branch>`; verify with `git -C <tree> remote -v` (origin push must be the DISABLE sentinel).
Full setup: the model checkout's `CLAUDE.md` §1a; [[feedback_model_source_push_fork_only]]. Contributing
upstream is a separate, deliberate PR.

## Footguns

- **Building the change before preserving the baseline (SHARED build tree)** — the branch protected the
  source and nothing protected the binary; on EcoSIM/PFLOTRAN/ATS the baseline executable is gone. Step 3.5.
- **Archiving a binary and never RECORDING it** — the archives are outside git, so an unrecorded one
  exists only as a directory nobody tracks, and every round citing it has provenance that cannot be
  checked. `--generate` after archiving, `--verify` (M1-M7) before trusting the ledger; step 3.5.
- **Trusting a build's exit status** — three consecutive false "exit 0"s in one session. Gate on the
  artifact (binary mtime, the changed modules' `.o`, zero `error:`), step 4.
- **A run pointing at the live build path** — a queued job resolves its executable at run time, so a
  rebuild between submit and start swaps it silently, and on a shared tree the rebuild need not be
  yours. Applies to the PRODUCTION ensemble as much as to a verification arm. Point every run at an
  archived binary and make the launcher refuse a `*/build/*` path; step 3.5(c) and step 5,
  [[feedback_bind_runs_to_archived_binaries]].
- **Attributing a fault from a routine name when the backtrace has no LINE number** — a release build
  carries no `-g`, so `addr2line` resolves to the routine and you fill the rest in by reading code.
  That is a guess. **Disassemble the faulting address** (`objdump -d --start-address=…`) and read the
  instruction; two minutes. Measured 2026-08-21: a SIGFPE was attributed to the one division in the
  routine, the faulting instruction was a `subsd`, and the resulting "fix" was inert against 79% of
  the failures — a wrong fix, a build and a full gate cycle. Confirm the exception class too, from
  MXCSR under `gdb` (`info registers mxcsr`), not from the signal name.
- **Reading a V0 pass as proof without checking the arms differed** — same binary twice passes perfectly.
- **Editing the anchor in place for a repro-sensitive change** — breaks the reproducibility baseline. Use an
  experiment branch for those; keep the anchor rebuildable.
- **Skipping default-off on a switch-gated change** — a change that alters baseline even when "off" makes the
  reference drift; the OFF run must be baseline-identical.
- **Trusting a run before V0-at-equality** — an "on" result is meaningless until the paired "off" run proves
  the harness reproduces baseline.
- **Assuming the mechanism moves the target** — build the gate (step 1) first; #16's A/B are the cautionary tale.
- **Assuming the scope is small / the framework mechanism exists** — the sketch under-counts. Map it from
  the codebase wiki first (it gives the file set with no tree walk), then grep every
  consumer and read the register/retrieve + state-coupling from source *before* editing; a structural change
  routinely spans several files + a restart-format change. Mirror an existing template, don't invent.
- **Pushing upstream** — a stray `git push origin`/`upstream` targets the community repo; the `DISABLE` guard
  blocks it, but keep the discipline.
- **Writing a pointer instead of a record** — "see the branch" is not a log. The case's model-evolution record must stand alone: mechanism, verification, commit, and what it means for the rounds.

## Cross-references

- **Sub-recipe:** `add-fates-parameter` (the "add a tunable/switchable knob" case — `EDParamsMod` scalar or
  `EDPftvarcon` per-PFT plumbing).
- Build reuse + paired-run pilots: `offline-testing-workflow` (Step 5 build reuse; the pilot pattern).
- Contract + memories: `E3SM_FATES_api43/CLAUDE.md` §1; [[feedback_model_code_comment_jing_tao]],
  [[feedback_model_source_push_fork_only]], [[feedback_performance_experiment_is_the_objective]].
- Model-dev-track adoption on main: `memory/dev_logs/20260709i_Model_Development_Track_Adoption.md`.
- Worked examples live on the **demo branch** (api-31): #16 `fates_max_plant_density`, #17 `phen_gddthresh_c`
  PFT-split — their logs live on the demo branch (under its `use_cases/{Model}_{Case}/memory/logs/`), not on main.

## Notes

- **Branch fit:** the *workflow* (branch-by-intent, default-off, paired verify, log-both-streams, fork-only
  push) is generic model-dev. The specific forks/paths are Jing's; the frozen-manuscript branch (demo) is
  stricter on step 0 (always an experiment branch).

