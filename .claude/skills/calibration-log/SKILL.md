---
name: calibration-log
visibility: public
category: calibration
description: Log interactive calibration work for a site under use_cases/{Model}_{Case}/memory/logs/. Two log types — a PHASE log (a diagnosis, screening, experiment design/result, refinement — recorded the same way the autonomous agent does, via PhaseLogger, so both modes' logs synthesize together) or a free-form SESSION log (exploratory work that does not map to a specific phase). Use when the user wants to record calibration or exploration work — "log this", "log this phase / diagnosis / experiment", "log this calibration session", "write a session log", "record what I explored".
modes:
  requires_fates: false      # logging convention; model-agnostic (PhaseLogger)
  nutrient_pathway: any
  scope: [logging]
  summary: "Site calibration/exploration logging via PhaseLogger; applies in every mode."
---

# Log Calibration Work (phase log or free-form session log)

Records the interactive agent's calibration/exploration work for a site under
`use_cases/{Model}_{Case}/memory/logs/`, so it lives alongside the autonomous agent's logs and
`tools/session_report.py` / synthesis reporting can process everything for a session together.

## Step 1 — pick the log type

| Type | When | How it is written |
|------|------|-------------------|
| **phase log** | The work maps to a Phase 0–7 activity (diagnosis, screening, experiment design/result, refinement, …) | `PhaseLogger` — identical format/naming to the autonomous agent |
| **session log** | Free-form / exploratory work that does **not** follow the phases exactly (an ad-hoc analysis, a data check, an idea) — which is fine | a plain dated note using the `YYYYMMDDx_Topic.md` convention |

Both land under the same session directory `use_cases/{Model}_{Case}/memory/logs/{stamp}/`, so synthesis
sees one session in one place. `{stamp}` = the orchestrator `session_id` (`YYYYMMDD_HHMMSS`) when a
run is active, otherwise a date stamp for the interactive session.

## Type A — phase log (via PhaseLogger)

Don't hand-roll the format, and **don't hand-roll the DRIVER either — use `tools/write_phase_log.py`.**

```bash
python tools/write_phase_log.py --phase 3 --payload <phase_results/{stem}/payload_phase3.py> \
                               --site-dir use_cases/<Model>_<Case>
```

The payload is a small PYTHON module (not JSON: the reasoning body is a long r-string and wants to stay one) defining exactly four names — `TITLE`, `COUNTERS`, `HANDSHAKE`, `LOG` — where `LOG` is the phase method's own kwargs minus `title`, passed through verbatim so the tool never has to know a phase's field names and cannot fork the contract when `PhaseLogger` gains one. **It is a thin front-end over the same `PhaseLogger` API the ONLINE agent uses**, deliberately: a second way to write a log would be a second contract.

**Why a tool rather than a per-case script.** The content of a phase log is the case's; the MECHANICS are A2MC's, and that is where the failures were. Measured 2026-09-07: **47 tracked copies** of `write_phase{N}_log.py` across two cases, 39 of them stem copies, and three distinct failures in a single session, all in the boilerplate and none in the content. `create_logger()` with no site **falls back to `use_cases/TEMPLATE`** and writes a log stamped `**Site:** TEMPLATE` that passes every conformance check; with `A2MC_AGENT_MODE` unset the log lands in the ONLINE nested layout while `topic_artifact_dir()` keeps the offline stem, which `PhaseLogger` warns about and then does anyway; and a descriptor slugified to two different lengths minted a `zd` folder against a `ze` log. The tool refuses the first, sets the mode before constructing the logger for the second, and **asserts the written log pairs with its folder** for the third, so a split cannot be committed rather than being found later by `check_stem_pairing.py`. Guards proven by negative control in `tests/test_write_phase_log.py` (removing a guard turns its test red).

The underlying library is still `tools/phase_logger.py`, and calling it directly remains correct for the online path and for anything the tool does not cover:

```python
# source use_cases/{Model}_{Case}/config/{site}_config.sh first -- since v2.306 it auto-sources its own
# machine config (a2mc_config.sh CIME/ELM-FATES, a2mc_noncime_config.sh non-CIME adapter). As the INTERACTIVE agent set:
#   export A2MC_AGENT_MODE=offline   → the flat memory/logs/{stem}.md layout (see "Offline layout" below)
from tools.phase_logger import create_logger

logger = create_logger()                 # resolves site dir from A2MC_USE_CASE_DIR
logger.set_iteration_context(            # the three-level counters (see CLAUDE.md)
    iteration=<skip+1, or 0>,            # REQUIRED positional arg; use 0 for Phase 0-2 (no inner loop)
    calibration_round=<round>,           # RR — outermost loop
    experiment_count=<exp_cycle>,        # EE — middle loop (Phase 3-6)
    skip_testing_count=<skip>,           # inner loop (Phase 3/4 only)
)
logger.log_diagnosis(title="PFT10 Fineroot Root-Cause", content=<markdown>, ...)
```
> **If an AGENT is running this, join the `source` to the command that needs it** — `source … && <command>`. A harness gives each shell call a fresh process, so a config sourced on its own is gone by the next call, and the script then reports its variables unset as though nothing had been sourced. A human at a terminal is unaffected. Full statement: `AGENTS.md` §"Source the config and run in the SAME command".



Per-phase methods: `log_design` (0), `log_exploration` (1), `log_screening` (2),
`log_diagnosis` (3), `log_hypothesis` (4) / `log_experiment_design`, `log_testing` (5),
`log_refinement` (6). Each applies the right section template from `templates/logging/`.

Lands at (**ONLINE / orchestrator run only** — a `session_id` is present):
```
use_cases/{Model}_{Case}/memory/logs/{stamp}/phase{N}_{name}/
    Phase 0–2 : r{RR}_{stamp}_Title.md
    Phase 3–6 : r{RR}_c{EE}_iter{II}_{stamp}_Title.md
```
`RR` = `calibration_round`, `EE` = `experiment_count`, `II` = `skip_testing_count + 1` (Phase 3/4).
Full convention: `CLAUDE.md` §"Session Logging Convention" and the `tools/phase_logger.py` header.

**Offline (interactive-agent) layout — THE DEFAULT FOR YOU, the interactive agent (docs/31).** You have
no orchestrator run / `session_id`, so this is your convention (the nested `{session_id}/phase{N}_{name}/`
form above is the online/orchestrator layout ONLY). Set `A2MC_AGENT_MODE=offline` (or `create_logger(...)`
with `agent_mode='offline'`). `PhaseLogger` then writes a **date-led flat topic-stem** — `logs/{stem}.md` with
`stem = YYYYMMDDx_phase{N}_{name}_r{RR}[_c{EE}[_iter{II}]]_{descriptor}` — and `topic_artifact_dir()`
gives the paired `phase_results/{stem}/` for figures/data. Track progress in the per-round
`workflow_state_offline_r{RR}.json` (`tools/workflow_state_offline.py`). The **online path is
unchanged**; this only switches on for the interactive agent. `session_report.collect_session_artifacts(include_offline=True)`
folds these flat logs into synthesis alongside session-scoped ones.

**A THIRD stream shares the same stem convention: `memory/model_evolution/{stem}.md`** (PI, 2026-08-24). It records **which model binary a round ran and what changed since the previous round** — stem `YYYYMMDDx_model_evolution_r{RR}_{descriptor}.md`, so it sorts and cross-references exactly like a phase log. It is written by `summarize-calibration-round` at the round close, not by a phase, and it exists because engineering provenance in the middle of a science narrative reads as an intrusion: the round report carries only a compact appendix table pointing here.

**It holds the case's model-update logs too** (PI, 2026-08-24): when a change to the model SOURCE is made for this case, the write-up goes here, beside the record of which rounds ran it. Keeping the mechanism and its effect on the calibration in one place under the case is what makes both readable by whoever picks the case up.

**A PHASE LOG IS A SYNTHESIS OF ITS `phase_results/{stem}/`.** The scripts and data in that folder PRODUCED the numbers; the log is the write-up of them. So the two are not two independent records that happen to agree: the folder is UPSTREAM and the log is DOWNSTREAM of it, and every number in the log is a citation of something in the folder. Three consequences, and the third is the one that bites:

- **Write the log from the folder**, not from recall of what the analysis returned.
- **Verify each number you carry forward against the script that computed it and the data file that holds it** — including numbers you are quoting from a PREVIOUS phase's log, which are citations of *that* phase's folder.
- **Where a log and a stem folder disagree, the FOLDER WINS** and the log gets a dated correction.

**MEASURED, and it is why this is stated rather than assumed.** One cycle's Phase-4 log carried three hand-entered gate values that appear in no artifact anywhere in the round, one wrong by 1e-4 relative. The next phase's control gate was EXACT by construction (a copied base), so quoting that log faithfully would have FAILED the gate and reported non-determinism in the model — a false and serious finding, produced by trusting a log over the folder behind it. It passed only because the gate was run against the prior cycle's data file instead. Same discipline as [[feedback_bind_derived_facts_to_their_source]], reaching the one place that memory does not: a number copied out of an artifact and into prose.

**Given that, the two artifacts have DIFFERENT jobs — do both fully.**
- **`log/{stem}.md` carries the ANALYSIS this session** — the reasoning, findings, discussion, the numbers
  with their interpretation, the conclusion, and the next action. Not a caption dump; the argument a cold
  reader reconstructs. (Analysis-phase logs also perform *first-hand* analysis, not a restatement of a prior
  log, `feedback_offline_logs_need_first_hand_analysis`.)
- **`phase_results/{stem}/` is a SELF-DOCUMENTING artifact folder** (mirror the `write-report` self-contained
  folder, `feedback_figures_over_tables_over_words`): for EACH figure ship **(1) the figure**, **(2) a
  caption/NOTES `.md`** (what it shows + how-to-read + provenance: which script produced it, from what data),
  **(3) the generating `.py` script SAVED into the folder** (written per the **`plotting`**
  skill — load it before the first `savefig`, not after; note this skill's only prior mention
  of `plotting` was an example inside the sample "Skills invoked" block, which is not an
  instruction and was read as decoration) (not run as an inline bash heredoc that vanishes),
  and **(4) the underlying data file**. **Start that `.py` by copying the case's TEMPLATE from
  `use_cases/{Model}_{Case}/scripts/` and adapting it here** — the adapted copy is the canonical script
  for THIS figure and stays with it; the template stays in `scripts/`. Writing a phase's script from
  scratch when a template exists is what produced 7 byte-identical duplicate scripts across one site's
  `phase_results/` folders. A script's SECOND use is the trigger to add it to `scripts/`. A future reader (or you next month) must be able to regenerate and
  interpret the figure without you. A lone figure with no caption / script / data is under-documented.

**Pass the TITLE as the descriptor to `topic_artifact_dir()`.** The artifact folder is keyed on a
descriptor you choose; the log is keyed on the `title=` you pass to `log_<phase>()`. They pair only
if both derive from the same string:

```python
TITLE = "R3 Screening Of The Alive Sub-Ensemble: One Target Fails, Not All Three"
d = logger.topic_artifact_dir(2, TITLE)     # <- the TITLE, not a separate phrase
...                                          # write figures + NOTES.md into d
logger.log_screening(title=TITLE, ...)       # same string -> same stem
```

Give them different strings and you get two stems and a log that does not match its own folder.
`topic_stem()` reuses an existing stem on disk (v2.274), which fixes the *process-boundary* case —
one run creates the folder, a later one writes the log — but it cannot rescue two genuinely
different descriptors.

**The log must SHOW its figures, not just name their folder** (PI, effective 2026-08-22). The two
artifacts above are meant to be read as ONE document — the PI opens `log/{stem}.md` and expects the
evidence to be there. `` `phase_results/{stem}/plot.png` `` in prose renders as a text path, so a log
that refers to "Figure 1a" while displaying nothing sends the reader hunting. **Embed every figure the
paired folder holds:**

```markdown
![](../phase_results/{stem}/R3_full_14799cases_alive_dead_structure.png)

**Figure 1. State the finding, not the axes.** What it shows, how to read it, and its provenance
(which script, from what data).
```

Empty alt text, bold `**Figure N.**` caption beneath — `feedback_report_figure_empty_alt_text`. The
path is relative from `logs/` (`../phase_results/{stem}/…`), so it resolves in-repo. Close the log with
an **Artifacts** table indexing every file in the folder and how to regenerate it.

`tools/check_offline_log_evidence.py` WARNs on a figure the folder holds and the log does not embed.
The rule is **dated**: logs stamped before `20260822` are grandfathered (45 of 82 predate it, and a
checker that is always red is a checker nobody reads), and the exempted count is printed so the backlog
stays visible.


**Phase 5 archives its JOB SCRIPTS into `phase_results/{stem}/submit_scripts/`** (PI, 2026-08-23). Copy, never move: the scheduler reads the operative copy from the run directory. The reason is that **the run directory is untracked scratch and gets cleaned**, while the submit script is where the **binary this run was bound to** and its **run-time hash assertion** are recorded. A log claiming its V0 gate passed, with no archived submit script, cannot show which executable produced the number, and on 2026-08-23 a cycle nearly ran against the wrong binary because the materializer emits the LIVE build path by default ([[feedback_bind_runs_to_archived_binaries]]). Archive one script per case plus one representative `runfile.nml`. **Phase 0 is deliberately EXEMPT.** Its job scripts are generated from the machine + round config by the materializer, and an ensemble is thousands of cases (one R3 round is 59,393), so archiving them would be both enormous and redundant: the config plus the generator already reproduces them exactly. Phase 5 is different because its handful of variants are hand-designed and hand-repointed, so nothing else records what actually ran.

**Update the STATE before you write the log — the order is load-bearing.** `PhaseLogger` **bakes the
`## Reasoning chain` block into the file at write time**, rebuilding it from
`workflow_state_offline_r{RR}.json`. Nothing rewrites a log afterwards, so:

```
1. st.add_decision(...) / add_evidence(...) / save()     <- state correct FIRST
2. logger.log_<phase>(...)                               <- chain baked in correct
```

Do it the other way and every stale pointer is frozen in the log permanently. Measured 2026-08-22: a
stem was renamed after the log was written, and the superseded stem stayed in **14** places until the PI
noticed. `check_offline_log_evidence.py` now ERRORs on a cited `phase_results/<stem>/` that does not
exist — at any age, since a dead pointer reads as a citation and sends a reader chasing it.

**Structural gate.** After writing ANY calibration log — either type — run:

```bash
python3 tools/check_calibration_log_conformance.py <the log you just wrote>   # 0 clean · 1 warn · 2 error
```

It asserts the stem, the header fields, and — for a **phase** log — *that phase's own* required
sections, read from `PhaseLogger._EXPECTED_SECTIONS` so the tool and the generator can never
disagree. It also fails a `Phase Handshake` left as the generated placeholder (an unfilled field
looks like a chain and resolves to nothing) and warns on a `Sections not provided` list. The
pre-commit hook runs it on **staged** calibration logs.

> **Do NOT use `tools/check_log_conformance.py` here.** That one governs the DEVELOPMENT streams
> (`memory/dev_logs*/`, `memory/ana_logs/`) and its contract is different — it wants
> `Summary`/`Problem`/`Solution`/`Files Changed`/`Verification` and a `Version`/`Branch` header,
> none of which a calibration log has. Pointed at a calibration log it reported 6 errors demanding
> sections that do not belong (measured 2026-08-14). Both tools now refuse the other's stream
> outright, so the mistake is caught rather than silently mis-served.

**Evidence gate (docs/33).** After writing an analysis-phase log run `python tools/check_offline_log_evidence.py
<log.md>` — it must **exit 0** (ERROR = no resolvable first-hand artifact = a restatement). It now also
**WARNs** when `phase_results/{stem}/` has a figure but is missing its caption `.md` / generating `.py` /
data file — clear those warnings too (the self-documenting-folder discipline above), don't just pass on exit 0.

## Type B — session log (free-form)

For exploratory work that doesn't fit a phase. Write a plain dated markdown note at the **session
root** (no `phase{N}` subdir):
```
use_cases/{Model}_{Case}/memory/logs/{stamp}/YYYYMMDDx_Topic.md
```
- `YYYYMMDDx` = date + a sequential letter (`a`, `b`, `c`, … for same-day notes — check existing
  files so you don't reuse a letter), `Topic` = Title_Case with underscores. Past `z` (27th+
  same-day), append a second letter keeping the `z` prefix: `za, zb, …, zz` (sort-stable — the
  offline stem does this automatically in `tools/phase_logger.py`; never `aa`, it sorts before `b`).
- Keep it light: a short header (**Date**, **Author**, **Type:** exploration/analysis) followed by
  free-form reasoning — what you looked at, what you found, evidence (cite specific cases/values),
  and any open question. No fixed section list; it is a working note, not a phase deliverable.
- **Author field** = `{A2MC_USER_NAME} with {coding-agent name}` — e.g. *"Jing Tao with Claude Code"*.
  `A2MC_USER_NAME` is captured at first run by `a2mc-init` (the greeting) and stored in the per-clone, gitignored `.me` via `python3 tools/whoami.py --set "<name>"`; both machine configs resolve the variable from there rather than carrying a name, because they are tracked and ship downstream, where a literal name would stamp someone else's logs;
  the coding-agent name is whatever harness you're running in. Fall back to the user's stated name, or
  `A2MC user with {coding-agent name}` if none was given. This is the **calibration-user** convention and
  it governs every log under `use_cases/{Model}_{Case}/memory/logs/`. A2MC *framework-development* logs use a
  different rule (author by environment); that rule does not apply here.

## The phase handshake — what you inherited, what you hand on

**A calibration log is not a dev log.** A dev log records a change. A phase log is a link in the
3→4→5→6→3 chain, and it carries the *reasoning* forward.

The autonomous agent hands the next phase a typed object (`reasoning/schemas.py`) — `Diagnosis` →
`Hypothesis` → `Experiment` — living in memory inside one run, so its chain cannot break. **You have
no such object.** Your phases are separated by days, sessions and compactions, so **the log is the
only channel.** If it does not carry the handshake, the next phase re-derives what this one already
concluded, which is the re-derivation the loop exists to avoid.

So an offline phase log must carry **more** than the online one: the field set *and* the narration.

`PhaseLogger` now emits the frame for you in offline mode. Set it before the `log_*` call, the same
way you set the iteration counters:

```python
logger.set_phase_handshake(
    inherited_from="20260716b_phase2_screening_r01 — ranked ensemble; best_case=CX1MG3, 2/3 targets",
    handed_to="parameter_recommendations + base_case_id (mirror the schema field names)",
    next_action="Phase 4: skip-test the P-retranslocation ceiling on existing Morris data",
)
logger.log_diagnosis(title=..., failing_targets=[...], ...)
```

### The chain accumulates — it is not just the previous phase

`PhaseLogger` also emits **`## Reasoning chain — round RR, through cycle EE`**, rebuilt from
`workflow_state_offline_r{RR}.json` on every log: the round's explorations, diagnoses, hypotheses,
experiments and standing decisions, **each naming the log stem that produced it**.

This is the point of the loop. Calibration **accumulates** — each phase builds on the one before,
each experiment cycle on the cycles before it — so a log showing only its immediate predecessor
cannot be checked for logical consistency; a reader would have to open ten files to see whether the
reasoning follows. With the chain, every phase log states what it stands on and is traceable end to
end without leaving the file.

**Your job is to keep it true.** The chain is only as good as what the phases recorded into the
state, so update `workflow_state_offline` after every phase (`calibration-discipline` already
requires it) with the finding, not a label. An entry reading "ran the sweep" contributes nothing to a
chain; "VRNXI 52 + CB6 soil reached plant_C 417, 1.6% below the 424 floor" does.

Note the per-log handshake fields are consumed after each write. That is not to prevent carry-over —
carry-over is what the chain is for — but because those three fields describe *this* phase's
position: reusing them would state, falsely, that the next phase inherited what this one inherited.

Name the **predecessor log stem**, not just the phase — a stem resolves, "the last diagnosis" does not.
On a **6→3 re-entry** also say which hypothesis was disproven and what changed, or the new cycle reads as a fresh start. That is the FLOOR; the full obligation is the rethink protocol in the Enrichment contract below, whose pathways are what `handed_to` should name.

## Enrichment contract — the template is a floor, not a form

`PhaseLogger` writes the skeleton; **you fill it.** In offline mode it also appends a
`## Sections not provided` list naming every expected section left empty, because each section is
emitted behind an `if <arg>:` guard — an unfilled one otherwise leaves no trace it was skipped, and a
thin call produces a short, well-formed, entirely plausible log.

- **A phase log is a LIVING record, not an end-of-phase write-up.** Start it when the phase
  starts and enrich it as you go. This matters most for the phases that are not "analysis":
  **Phases 0 and 5 both put simulations on a scheduler**, so both carry the run-and-watch spine —
  Submission (job/array IDs) · Simulation Status · Monitoring Armed · Failures and Restarts —
  each paired with its artifact in `phase_results/{stem}/`. They differ in what surrounds it:
  **Phase 0** materializes an ensemble, so it adds Sampling Design · Cases Materialized ·
  Verification Plots. **Phase 5** runs a handful of VARIANTS designed from the hypothesis the
  inner 3↔4 loop produced, so it adds Experiments Designed · **V0 Reproducibility Gate** ·
  Results Preview (does each new test look sane?) · Results Summary. "Cases Materialized" is
  phase-0 vocabulary and is deliberately not asked of phase 5. Deferred to the end, that operational detail is simply gone: nobody
  reconstructs a failed-case list or a restart command from memory a week later.
- **A Phase-6 log that routes 6→3 must carry the RETHINK, not just the decision.** `phase6-refinement` Step 4 owns the protocol; the log is where its output has to land, because the next cycle reads the log and not the state enum. Record all six: the synthesis of THIS cycle (phases 3-6, separating what it ESTABLISHED from what it merely tried), the re-reading of Phases 1 and 2 against that synthesis, whether the BASE is still right for the question now being asked, whether the BINDING TARGET has moved, which lever CLASS the round has now exhausted, and for each refuted lever which DIRECTION was moved from a base with which SIGN of miss and whether that still applies. Then record the **NEW PATHWAYS** it emits, each with its lever class and its falsifier, and name them in `set_phase_handshake(handed_to=...)` so Phase 3 starts from them. A log that records `rethink_6to3` and nothing else has documented a counter increment, which is what the route was before the protocol existed: measured on one round, three consecutive rethinks carried one base and one target framing forward and the cycle that finally re-examined them found both wrong.

- **A placeholder is a finding, not a state.** `_(not provided — fill, or state why it does not
  apply)_` means either fill it or replace it with the reason it does not apply (PFLOTRAN has no
  Cross-PFT Conflicts; one case has no Comparative Case Analysis). Both are acceptable; leaving it is not.
- **Cite evidence for every substantive claim** — the result file, the figure, the curated-knowledge
  entry, or **source `file:line`**. `LitterFallMod.F90:756` is a different quality of claim from
  "the ceiling appears to bind", and mechanism-level reasoning in Phase 3 is where that difference decides
  whether the next phase tests the right thing.
- **Depth is not gated, and that is deliberate.** A gate demanding non-empty sections manufactures
  filler, and a hollow section that reads like analysis is indistinguishable from real analysis — which
  a visible placeholder never is. What IS checked is structural: `check_offline_log_evidence.py`
  (a first-hand artifact exists) and the log naming its predecessor and a next action.

## Both types — record what you CONSULTED, not just what you did

Add a short **`## Skills and memory invoked`** block near the end of the log (just before any
cross-references). It applies to phase logs and session logs alike.

**For a Type A phase log, put it in the `content=` markdown you pass to `PhaseLogger`** — do not
edit the generated file afterwards. The per-phase methods own the header, filename and section
template; `content` is free markdown, so the block travels inside it and the output still matches
the autonomous agent's format. For a Type B session log, just append it before you finish.

```markdown
## Skills and memory invoked

- **Skills:** `phase3-diagnosis`, `plotting`
- **Memory:** `feedback_timeseries_plots_during_diagnosis`, `reference_l2fr_is_fineroot_per_leaf`
- **Memory written:** `feedback_new_thing_learned_here`  *(memories this log CREATED or CHANGED — distinct from **Memory:** above, which lists memories APPLIED. Each one's `**Source:**` must name this log back; both checkers verify the pair.)*
- **Knowledge consulted:** RAG `api-43-1` (2 queries on ECA uptake); curated discovery
  `kougarok_allocation_paradox`
- **Gaps / misfires:** nothing in curated knowledge covered the P-retranslocation ceiling,
  hence the candidate below.
```

Rules:

- **Name things exactly** — the skill directory name, the memory's `name:` slug, the RAG profile,
  the curated-knowledge key — so the entries are greppable rather than prose.
- **List what you actually followed.** A skill you opened and abandoned belongs under
  *Gaps / misfires* with the reason, not under *Skills*.
- **"None" is a legitimate and informative answer.** Write it rather than dropping the section: a
  substantial diagnosis that consulted no knowledge source is itself a finding, and usually a
  prompt to go check the knowledge base before trusting the conclusion.
- **The Gaps line is the load-bearing one.** A skill that misled feeds `refine-skill`; a lesson
  with no knowledge entry yet is a **candidate** for `inject-knowledge` / `curate-knowledge` —
  a candidate, never a write. Curated knowledge stays human-gated, and a diagnosis is not
  curated knowledge until an experiment verifies it
  ([[feedback_no_kb_injection_before_verified_test]]).

**Why:** a calibration log records the evidence for its conclusion but not which knowledge the
conclusion was built on. That hides the two failure modes that matter most here — a hypothesis
formed without checking the knowledge base, and a conclusion inherited from a knowledge entry
that has since gone stale.

## Notes

- These are **run-state** logs (site-specific calibration data) — not synced to the public demo.
  The value is local synthesis across a session.
- Do **not** re-implement the phase naming/section logic here; it lives in `tools/phase_logger.py`
  and this skill follows it.

