---
name: write-report
visibility: public
category: authoring
description: Write a comprehensive, integrated, self-contained report on an arbitrary topic for a human reader (PI / collaborator / reviewer) — a crash/bug investigation synthesis, a mechanism study, a cross-cutting result write-up. Structures it for a ZERO-context reader (outline → executive summary → sectioned narrative → embedded figures with captions → provenance), gathers citation-backed facts first, and reconciles contradictions across source logs. Use on "write a report", "write up X for the PI/collaborator", "make an integrated report on X", "summarize this investigation into a report", "document the whole X arc". NOT the standardized single-round summary (use summarize-calibration-round) and NOT journal-register prose (use manuscript-writing-style).
allowed-tools: [Read, Glob, Grep, Write, Edit, Bash]
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [analysis]
  summary: "Integrated, self-contained report for a zero-context human reader. Model-agnostic."
---

# write-report — an integrated, self-contained report for a human reader

A report is read by someone with **zero project context** — a PI, a collaborator, a reviewer, your
future self. It must carry them from "what is this" to "what did we find and how do we know" without any
prior knowledge of the codenames, the pipeline, or the logs it's distilled from. This skill is the
structure + discipline for that; the pieces (figures, PDF) come from sibling skills.

> **Not this skill:** the **standardized** single-round calibration summary → `summarize-calibration-round`
> (a FIXED deliverable: combined/TRANS ensemble graphs + evaluation + Morris μ*). That is
> a different artifact from the **ROUND report** this skill names below, which synthesizes the round's
> CYCLE reports into an arc plus a next-round plan; where both apply, the standardized one supplies
> figures the round report cites. **Journal-register
> manuscript prose** → `manuscript-writing-style` for the REGISTER — but **borrow its Rigor,
> Transparency and Self-check sections here**: they are not journal-specific, and a report makes
> scientific claims to a scientific reader exactly as a paper does. A short **internal log** (shorthand OK) → `log` /
> `calibration-log`. This skill is the **comprehensive, topic-agnostic integrated report** — and it names two recurring
> calibration deliverables explicitly, the **CYCLE report** and the **ROUND report**; see the section
> immediately below the discipline.

## The discipline (non-negotiable — `<auto-memory>/feedback_report_writing_self_contained`)

- **Zero-context reader.** Assume the reader knows nothing about A2MC internals — this governs
  A2MC-internal codenames and the report's own self-containedness, not a standing team's own
  domain vocabulary, and **never the register** (next bullet). Define each such term **inline on
  first use**; there is no glossary block to defer it to (Structure step 2).
- **Executive summary first** — the whole story (problem → cause → fix → outcome) before any detail.
- **SCIENTIFIC REGISTER, and "zero-context" is not a licence to simplify the science** (PI, 2026-09-09).
  The reader is a scientist who does not know THIS project, not a reader who needs the science
  translated. Three consequences. **Name the instrument and the quantity**, never a paraphrase of what
  the quantity means: *"eleven years of eddy-covariance CO2 and water-vapour flux measurements"*, not
  *"eleven years of measurements of how much carbon it takes up and how much water it loses to the
  air"*. **State findings, not verdicts on the question**: *"all three annual targets fall inside the
  acceptance band"*, not *"the answer to the question as posed is yes, comfortably"*. **Quantify the
  claim in the sentence that makes it**: *"the round's main output is a demonstration that no
  parameter can fix it"* is an assertion until it carries the number and the mechanism it rests on.
  A sentence that would not survive peer review reads as unserious about the result, whatever the
  result is.
- **Define-or-avoid every codename/jargon** — ADSP, PFT, Morris, prescribed-P, V0, PARTEH, etc. Either
  define it inline on first use, or don't use it. No glossary block (Structure step 2).
- **Every claim is a complete finding→mechanism→evidence sentence** — the plain finding, *why* (mechanism),
  and the *evidence* (a number, a figure, a cited source). No isolated jargon ("72 PARTEH failures are
  restart-eligible" fails; a stranger can't parse it).
- **Stranger test:** could someone outside the project read a section and understand the claim + how you
  know it? If not, rewrite.
- **An unverified claim is LABELLED, never stated flat.** If a claim is not backed by data, a citation
  or stated logic, frame it as a hypothesis, an assumption or a limitation. "Wiring the file changes
  the baseline" written before measuring it is the failure this prevents (2026-08-17, EcoSIM_Lusignan).
- **Every quantitative claim carries its uncertainty.** An estimate without one is incomplete. A phase
  shift reported as "+13 days" whose year-to-year SD is 16 days, and which is negative in 2 of 11
  years, misleads a reader who then cannot find it in the data — which is exactly what happened when
  the PI checked that figure. Report mean +/- SD (or a CI) and n, and say which estimator you used
  when more than one is defensible.
- **Keep data, model inference and interpretation grammatically distinct.** "The observations show X",
  "the model implies Y", "we read this as Z" are three different claims with three different
  warrants; a sentence that blends them cannot be checked.
- **No em dashes (—).** Do not use the em dash character in report prose (user preference). Use a comma, a
  colon, parentheses, or split the sentence instead. En dashes in numeric ranges (2000-2004) are fine.
  Applies to the rendered PDF too, since the em dash carries through.
- **No ~99-column hard wrap — write ONE PARAGRAPH PER LINE** and let the editor or renderer wrap
  (user preference). This is not only taste: markdown **joins consecutive lines into one paragraph**,
  so a hard-wrapped metadata block (`**Status:**` / `**Date:**` / `**Author:**` each on their own
  line) collapses into one flowing line in every renderer, GitHub included, and needs explicit hard
  breaks to survive. Retrofitting is expensive — un-wrapping the EcoSIM_Lusignan pre-R1 report took a
  purpose-written reflow script with a content-preservation assertion, and it still broke the header
  block on the first pass. Tables, fenced code blocks and byte-budgeted files are exempt.
  (`<auto-memory>/feedback_prose_no_em_dash_no_hard_wrap`)

## Structure (the recurring skeleton, adapt, don't pad)

1. **Title + a header block** — a one-line status/scope (e.g. "Fix validated; recovery in progress"), the
   date, and an **author/provenance line**. The author line is REQUIRED and is exactly `**Author:** Jing
   Tao with A2MC` (no host / machine suffix). The report-specific author is **A2MC**, not Claude, because
   these `reports/` are public-facing A2MC deliverables and credit the framework that produced them. This
   is deliberately DISTINCT from every other artifact (dev/ana logs, scripts, commits), which keep the
   `CLAUDE.md` author-field convention (`Jing Tao with Claude` / `Jing Tao`). The `with A2MC` form applies
   ONLY to `reports/` written by this skill. Note the companion report/log it complements so the reader
   knows the boundary.
2. **Outline** — a plain table of contents (section numbers -> titles, with notable
   subsections) so a reader can navigate without scrolling blind. Add it for a long,
   multi-section report (roughly 5+ top-level sections, or anything meant to be read as a
   rendered PDF). Skip for a short, single-arc report where the section list is already
   visible at a glance.
   **Do NOT write a `## Reader's key` / glossary block** (PI, 2026-08-24). It was an
   allowed affordance until then and is now removed: in practice it front-loads a wall of
   definitions the actual readers already know, and it let jargon into the body on the
   excuse that a glossary existed. **The obligation it was standing in for does not go
   away** — every codename and domain term is still defined *inline on first use*, per the
   discipline above, and the stranger test still applies. Define it where it is used, not
   in a list nobody reads twice.
3. **Executive summary** — plain-language, the whole arc in a few paragraphs.
4. **Sectioned narrative** — background/context → the problem & why it mattered → investigation /
   diagnosis → the solution → verification → results → significance & open items. Each section ends with an
   **Evidence** pointer (the log/figure/number it rests on).
5. **Embedded figures with captions** (see FIGURES below) — placed at the section they illustrate.
6. **Skills and memory invoked** — REQUIRED since 2026-08-24 (PI), matching the same section
   `calibration-log` and `log` have required for months. A report records the evidence for its
   conclusions and never which capability surface produced them, so a wrong turn caused by a stale
   skill or a missing memory leaves no trace, and a skill nobody invokes looks identical to one that
   works. Place it just before Provenance:
   ```markdown
   ## Skills and memory invoked
   - **Skills:** `summarize-calibration-round`, `compare-calibration-rounds`, `plotting`
   - **Memory:** `feedback_figures_over_tables_over_words`, `feedback_report_writing_self_contained`
   - **Gaps / misfires:** nothing in the skills covered X, hence the candidate below
   ```
   Same rules as the log streams: **name skills and memories exactly** (directory name, memory slug)
   so the entries are greppable; **list what you actually followed**, with anything opened and
   abandoned under Gaps with the reason; and **"None" is a legitimate and informative answer**,
   written rather than omitted. The **Gaps line is the load-bearing one** and feeds `refine-skill`.
7. **Provenance / artifacts** — the source logs, commit hashes, data files, and the figure-regen script,
   so every claim is traceable and the report is reproducible.
8. **Cross-references** — link companion reports/logs; **cross-ref, don't duplicate** their content.

**The outline is a STORY TO BUILD, not a set of boxes to fill** (PI, 2026-09-09). The sections in order must read as one argument, each one standing on the one before: what the model gets wrong and why it matters, what could be established without new work, what was therefore hypothesised and tested, what the system is now known to do, what that leaves open. A section that only reports its own contents is a box filled; the reader is then left to assemble the argument, and the report's central finding ends up stated in no section at all. Write the connective sentences deliberately — each section opens by saying what the previous one left unresolved.

## The two calibration deliverables this skill names

Most reports this skill produces are one-off. Two are **recurring, structural and nested**, and
both were being written thinner than the work behind them because nothing said what they must
cover. They are named here so their scope is a contract rather than a judgement call.

```
phase logs + phase_results/{stem}/     one per phase, per inner-loop ITERATION
        │  (the evidence: figures, captions, canonical scripts, data)
        ▼
CYCLE REPORT      one per experiment cycle (Phase 3→4→5→6)
        │  synthesizes EVERY log and EVERY phase_results/ folder of that cycle
        ▼
ROUND REPORT      one per calibration round
           synthesizes the CYCLE REPORTS, not the raw logs again
```

**The nesting is the point.** A cycle report that re-derives from raw logs duplicates them; a round
report that re-derives from raw logs duplicates every cycle report. Each layer synthesizes the layer
directly beneath it and **cites** the one below that.

**Where a report's OWN script lives.** A report that only cites existing figures needs no script. A report that generates NEW artifacts synthesizing across cycles or rounds keeps that script **with the report it serves** — the artifacts belong to no phase stem, so there is no stem to put it in. The canonical-script rule (`calibration-discipline` item 2) is not in tension with this: it governs a PHASE's figure scripts, and it bites when a report copies an existing stem's script and edits it there. When a cited figure needs changing, go back and fix the canonical script in its stem, then regenerate.


### The CYCLE report (one per experiment cycle)

Written at cycle end (per-cycle checklist item 7 in `calibration-discipline`). It must carry, and be
checkable against, all four of:

1. **The whole inner loop, iteration by iteration — not just the last one.** Phase 3↔4 is the
   skip-testing loop and it runs up to `--max-skip-testing` times *within one cycle*. Each iteration
   asked something and answered it on existing data, at no compute cost, and those answers are what
   justify the experiment the cycle finally ran. A report that mentions only the surviving hypothesis
   throws away the reasoning that selected it, and leaves a reader unable to tell a well-aimed
   experiment from a lucky one. **State per iteration:** what was investigated, what the skip-test
   returned, and whether it confirmed, refuted or refined the hypothesis. Measured across one
   campaign's three rounds: 46 phase-3/4 logs at `iter01` and 4 at `iter02`, none higher, against a
   cap of 10 — so a report covering "the iteration" was silently covering all there was, and the
   under-use of the free loop was invisible in every report written.
2. **Every hypothesis tested, and with which simulations.** Name the hypothesis, its falsification
   bar as Phase 4 recorded it, the variants that tested it with their actual parameter values, and
   the job identifiers. A hypothesis whose bar is not restated cannot be ruled CONFIRMED or REFUTED
   in front of the reader; they have to take the verdict on trust.
3. **What the simulation results actually say** — per variant, per **scored target**, against the
   measurements. Not a single composite score and not one target of several: an experiment that
   raises the target it aimed at while pushing two others out of band has failed, and a
   single-target figure cannot show it.
4. **The verdict, and where the loop goes next WITH THE REASONING THAT SENDS IT THERE** — CONFIRMED / PARTIAL / REFUTED against the Phase-4 bar, the mechanism learned, and the routing (rethink 6→3, redesign 6→0, converge).
   **On a rethink the routing is not a label, and a report that prints one has stopped a paragraph early.** `phase6-refinement` Step 4's rethink protocol produces a synthesis of the cycle, a re-reading of Phases 1 and 2 against it, a base and binding-target re-examination, a lever-CLASS verdict, a DIRECTION audit of every lever the round believes it refuted, and NEW PATHWAYS each with its falsifier. Carry at least the class verdict, any direction still untested, and the pathways into the report: a reader who cannot see why the next cycle attacks what it attacks cannot tell a redirected campaign from a stalled one, and those two look identical from a list of refutations.
   **Draw this from the Phase-6 log rather than deriving it again.** The protocol's item 1 produces exactly the synthesis this report needs and says to write it once; the report's job is to present it to a reader with no project context, not to reconstruct it from the raw logs.

**ENFORCED since 2026-09-09: `tools/check_cycle_reports.py` asserts that every CLOSED experiment cycle has one.** A cycle is closed when its `_phase6_refinement_r{RR}_c{EE}_` log exists; the check looks for a directory under the case's `reports/` naming that round and cycle, accepting `c00`, `c0`, `cycle0` and `cycle13` because all four are live in this repo. It WARNs rather than blocks (six pre-existing gaps sit in one case), and it carries an anti-silent-pass guard that ERRORS if either naming convention moves, because a checker reporting clean forever is worse than none. **Signal:** three cycles of one round closed with no report, the omission was written into the round summary as "recorded as debt rather than written", and the round report then re-derived from raw phase logs -- the anti-pattern this section names. Every other Phase-6 requirement had a checker; this one did not.

### The ROUND report (one per calibration round)

Written when the round closes — at the cycle-limit or at convergence, per the per-round checklist. It includes what phase 0, phase 1, phase 2, and the 1st phase 3 (diagnosis) have analyzed, discoveried, and recommended. Then, it
**synthesizes the cycle reports**: the arc across cycles, which levers were established and which retired, what each cycle's failure taught the next, and the residual gap. It does **not** re-narrate each cycle from raw logs — it cites the cycle reports for that.

> **"Synthesize, do not re-narrate" governs the NARRATIVE, never the SCIENCE.** What stays down in the cycle report is the blow-by-blow: which iteration asked what, which job ran when, how the cycle changed its mind. What must travel UP is every mechanism the round established about the SYSTEM. The four things the paragraph above lists — arc, levers established and retired, what each failure taught, residual gap — are all process-shaped, and a writer executing that list faithfully produces an excellent account of how the round reasoned and no account of what it learned. Read the list as a floor, not a ceiling, and see the required mechanism section below. Measured on one round report: its cycle report named the round's controlling variable twenty times, the next cycle report once, and the round report zero, while the round's whole finding was that this variable split two solutes from one source. The report passed every conformance check at every commit.

**TWO SKILLS RUN BEFORE THIS REPORT IS WRITTEN, AND THEY ARE STEPS, NOT SUGGESTIONS** (PI, 2026-08-24):

1. **`summarize-calibration-round`** — the standardized single-round bundle (ensemble figures, evaluation against targets, the sensitivity screen). Its output is this report's figure and evaluation input.
2. **`compare-calibration-rounds`** — the cross-round bundle. **This one is easy to skip and must not be**, because a round report has to carry *what earlier rounds established*, not only what this round did. Its four bullets below (parameter add/remove, bounds recenter, base update, residual split) are **all cross-round questions**: which parameters earlier rounds already tested and refuted, where the bounds came from and what still carries provisional debt, what was baked into the base and when, which residuals were already routed. **A round report written from this round's artifacts alone will re-propose a refuted lever.** Measured: one round summary proposed adding two parameters that earlier rounds had already tested and refuted with named mechanisms, and both errors survived every checker because nothing in the round-close path opens a prior round (`memory/dev_logs_adapterkit/reflection/20260824a_*` and `20260824b_*`).

**FIVE SKILLS ARE REQUIRED FOR A ROUND REPORT, AND THE REPORT MUST NAME THEM** (PI, 2026-09-05). `summarize-calibration-round`, `compare-calibration-rounds`, `write-report`, `calibration-goal` and `calibration-discipline`. They are the pipeline a round report is the OUTPUT of: the standardized bundle with its two required tables and its mechanism inventory, this report contract, the driver that reached the round close, and the per-cycle discipline that produced the artifacts being synthesized. **Including the FIRST round.** "Nothing to compare yet" is true only of `compare-calibration-rounds`'s Deliverable 2, the cross-round figures, which a first round records as not applicable. Its other deliverables all have content at R1, and the one-column ledger a first round produces is the baseline every later round is checked against; skip it and R2's comparison has no prior state to read.

Name them backticked on the `**Skills:**` line of the report's own capability section. **`tools/check_report_conformance.py` raises an ERROR, not a warning, when one is missing, and the remedy is to run the skill and REDO the report, not to add the name.** A round report assembled from whatever was on disk, rather than produced by this pipeline, is how one lost its own central mechanism while passing every check. A newly ADDED report additionally has its claims verified against the session transcript by `check_skill_claims.py`; edits to an existing report are exempt, because a report's capability section describes the session that wrote it and a later session legitimately invokes different skills.

**THE ROUND REPORT HAS A CANONICAL OUTLINE: SEVEN SECTIONS** (PI, 2026-09-05). Use these names. They are not a suggested ordering of thirteen headings, they ARE the sections; everything else is a subsection under one of them.

```markdown
1. Executive summary
2. The calibration design                  <- what is being calibrated + the design and what actually ran
3. Screening results and sensitivity       <- what the ensemble alone established + the sensitivity section
4. Mechanism and hypothesis testing        <- the cycle ledger, the arc across cycles, the MECHANISM, the parameter reference
5. Improvement and gained knowledge        <- what the round achieved, its qualifications, held-out validation
6. Open questions and next-round plan      <- the enumerated questions + the plan they feed
7. A2MC self-check and provenance          <- Skills and memory invoked + provenance + the model-evolution appendix
```

**SECTION 1 STATES THE OUTCOME QUANTITATIVELY, INCLUDING THE CLOSING STATUS** (PI, 2026-09-09). The executive summary of a round report has a shape, and it is not a summary of the sections: what the ensemble already achieved before any experiment, what it did NOT achieve and by how much, how far the round's cycles moved that deficiency in percent, through which mechanism the movement came, what the round's principal finding is about the system, and what the case's status now is including the conditions under which it would be reopened. Every one of those is a number or a named mechanism. A summary written instead as a verdict on whether the round succeeded says less than any of its own sections.

**SECTION 2 ESTABLISHES THE CALIBRATION PROBLEM WITH A FIGURE** (PI, 2026-09-09). The design cannot be judged without the deficiency it was designed against, and prose describing a seasonal-cycle mismatch is a claim the reader must take on trust. Embed the pre-round observed-versus-simulated comparison, discuss it per the figure rule above, and read the design off it: which processes the parameter list covers, why those and not others, what was deliberately left out, and what the design therefore could and could not have fixed. The figure usually already exists, in the case's pre-round analysis report, so this is a citation rather than new work.

**SECTION 5 MUST DELIVER THE ROUND'S PRODUCT: the ranked SET of calibrated parameterizations, with a link and a PROVENANCE table** (PI, 2026-09-09). A calibration's product is its parameter sets, and a close that describes only the round's reasoning has not handed the result over. The section needs:

- **the top-N table, ranked on the criterion the round actually STEERED BY and gated as the round gated it.** Not automatically the scored one: a scored criterion that every configuration already satisfies cannot rank them, and ranking on it returns what the round spent its cycles rejecting. If the round refused a configuration on physiological or structural grounds, carry that gate into the table.
- **any second criterion in the same table**, with the disagreement stated rather than resolved silently.
- **a PROVENANCE row per entry** — its origin, and where it is discussed — so a reader reaches the cycle report instead of reconstructing it. Say which entries were never individually examined: in the set because it SCORES is a different claim from in the set because the round studied it.
- **a link to the `{stem}_FINAL_CONFIGURATION/` bundle** (`phase6-refinement` element 7), and **the cumulative figure with the set drawn on it**, so the delivered configurations sit on the same axes as the experiments.
- **every metric in the table computed by the round's OWN function, imported, never rewritten** (`phase6-refinement`, the never-reimplement rule, which covers unscored metrics too). A report that recomputes the criterion it ranks on can disagree with every number the round recorded, and the disagreement looks like a finding.

**Section 4 is the point of the change.** The cycle ledger, the arc, the mechanism and the parameter reference are one argument: what was hypothesised, what was tested, what came back, and what the system is therefore now known to do. Scattered across four top-level headings they read as four bookkeeping exercises, and the mechanism, which is the only one of the four that is a scientific result, sits between two tables looking like a third table. Keep them together and the section states a finding.

**Why the names changed.** The previous outline grew one heading at a time as requirements were added, reaching thirteen top-level sections with titles like *"What was being calibrated, for a reader with no context"* and *"The design, and what the round actually ran"* — descriptions of a heading's purpose used as the heading. A reader scanning a contents list wants nouns. Two headings that answer one question are one section with two subsections.

**Keep `### Skills and memory invoked` as a bare subsection heading** under section 7, with no number before the words: the conformance checker anchors on `^##+\s*Skills and memory invoked`, so `### 7.1 Skills and…` fails it.

**A MECHANISM SECTION IS REQUIRED: WHAT THE ROUND ESTABLISHED ABOUT THE SYSTEM** (2026-09-05). Separate from the arc, and separate from the tables. It states each mechanism the round established as a finding→mechanism→evidence claim, with a `file:line`, an artifact path or a named log for every number. Its source is the round's **first Phase-3 diagnosis** plus every later diagnosis and refinement, which is the requirement already stated in this section's opening paragraph — this section is where that requirement is discharged, so it stops being the only content obligation with nowhere to live.

**Why it needs its own section, and this is the transferable part.** The two required tables are indexed by what the round MANIPULATED (the parameter reference: one row per parameter) and what it SCORED (the cycle ledger: result per scored target). A mechanism is frequently neither. Three shapes have no row available to them by construction:

- **A relation between two parameters.** The parameter reference's mechanism column is one cell per row, so it holds what a knob DOES ("precipitates manganese"), not how two knobs oppose each other. Split across two rows, the interaction itself disappears.
- **A state variable that is neither sampled nor scored.** It has no row in either table, so its absence leaves no hole a reader or a checker can see. In the measured case this was the round's master variable.
- **A finding that the parameter list was WRONG.** A table built from the parameter list cannot naturally represent what the list omitted. The parameter reference can carry the row with a "not sampled" range, and should, but the reason it was wrongly excluded is a paragraph, not a cell.

Signal: a round report described an iron and calcium trade-off in four places, correctly, and never once named the pH dependence that causes it, the fixed source ratio that creates it, or the saturation asymmetry that splits it. All of it was in that round's Phase-3 diagnosis with source citations. The omission was invisible because every other requirement in this section is a named structure with a checker, and this one was a clause in a sentence.

**READ THE ROUND'S OFFLINE STATE FILE BEFORE WRITING, NOT ONLY THE CYCLE REPORTS** (2026-09-05). `use_cases/<Case>/memory/workflow_state_offline_r{NN}.json` is the reasoning chain in machine-readable form: `evidence.diagnoses[]`, `evidence.hypotheses[]` and `evidence.experiments[]` each carry a stem, an artifact path and a `one_line` written when the finding was fresh, and `decisions[]` carries every finding recorded as it was established. `compare-calibration-rounds` already reads this file for its `decisions`; this report needs it for the evidence entries too, because a `one_line` is the finding at full strength before four layers of synthesis have thinned it. Measured on the round above: **every one of the eight quantities missing from the report was sitting in that file**, in one diagnosis `one_line`, alongside 156 recorded decisions. Nothing in the report-writing path opened it.

**A SENSITIVITY FIGURE AND DISCUSSION ARE REQUIRED, WHATEVER THE SAMPLING METHOD** (PI, 2026-08-24).
The round report carries them; step 1 produces them. A round whose designed estimator failed to
converge does **not** get to omit the section: it falls down `summarize-calibration-round`
guarantee 3's ladder (the design's own estimator, then the controlled single-parameter pairs the
design already contains, then regression or rank correlation, then per-parameter quintile response)
and says which rung it is on and why. Where deaths are non-trivial the discussion covers
**viability** as its own dimension, since a section computed on the surviving cases alone discards
most of what such a round measured. Signal: one round summary shipped with no sensitivity
figure at all because its Saltelli estimator was unusable, while that round's own Phase 1 had
**already computed** usable rankings, a point-biserial viability screen and per-target rankings
among the survivors, and left them in a JSON nothing plotted. The gap was between computed and
presented.

**AN OPEN-QUESTIONS LIST IS REQUIRED** (2026-08-25). The round report **ENUMERATES** the questions this round could not answer; `round-housekeeping` step 4 then **CARRIES** them forward as a named artifact the next Phase 0 reads. That split is deliberate: this report already holds the evidence and the next-round plan, and the housekeeping is what hands a named artifact onward, so neither needs a third document.

Each item needs **what would settle it** and **what it blocks** — a question with neither is a musing, not a task:

```markdown
## Open questions this round could not settle

| # | Question | What would settle it | What it blocks |
|---|---|---|---|
| 1 | Is the establishment bottleneck physically realistic, or an artifact of the bounds? | Site seedling-density observations, or a probe at literature-sourced GRDM | Whether R4 should widen the establishment levers or accept the regime |
```

Signal: one round's genuine open items — an arithmetic check, whether a bottleneck was realistic, whether an exchange rate transfers to a second base — existed only as **sentences scattered through prose**, so nothing carried them into the next design and nothing could tell a settled question from a forgotten one.

**A MODEL-EVOLUTION APPENDIX TABLE IS REQUIRED WHEN THE MODEL SOURCE CHANGED SINCE THE PREVIOUS ROUND** (PI, 2026-08-24). **At the END, not in the narrative.** Which commits the round's binary carried, what each updated, its kind, which rounds have it, and its effect on a run, plus one-line comparability statements. **The detail belongs in the case's `memory/model_evolution/{stem}.md` record, not here**: a first attempt put it in as a numbered section near the front and the PI's objection was that engineering provenance reads as an intrusion in a science report. One sentence in the narrative names the binary and points at the appendix. Produced by step 1.

**TWO TABLES ARE REQUIRED** (PI, 2026-08-24). Both were written by hand in earlier round reports and are now contract, because they are what a reader and the next round actually use. **They are PRODUCED by step 1, `summarize-calibration-round`, and REQUIRED here; this skill does not derive them.** If they are missing when the round report is written, the missing work is in step 1, and the parameter reference's cross-round status column is filled in step 2 by `compare-calibration-rounds`. The direction is: cycle reports feed step 1, step 1's synthesis and tables feed step 2 and then this skill, and this skill writes the narrative.

**The CYCLE LEDGER table.** One row per experiment cycle, including the screening/design cycle. A reader must be able to see what each cycle asked, what it moved, and what came back, without opening a cycle report.

```markdown
| Cycle | Question / hypothesis, and its falsification bar | Parameters varied and values tested | Result (per scored target) | Verdict and what it taught |
|---|---|---|---|---|
| **3** | Is the too-small seed the cause? …bar: any cell establishes | GRDM 1e-4, 5e-4, 1e-3, 5e-3 gC/seed x fCHLMESO {0.05, 0.6} | best 1.7 gC/m2, 0 of 8 establish | REFUTED. Seed size sets the starting point, not survival |
```

**EACH HYPOTHESIS IN THE LEDGER IS WRITTEN AS A COMPLETE SCIENTIFIC HYPOTHESIS** (PI, 2026-09-09). A cell reading *"a compensating pair, microbial maintenance up and decomposition down"* or *"SPOSC up, the direction cycle 0 did not try"* names an INTERVENTION, not a hypothesis: it says which knobs moved and in which direction, and leaves the reader to guess what was believed about the system and what would have falsified it. In a scientific report every row states **what is proposed to be true of the system, through what mechanism, with what predicted observable consequence, and the bar that would refute it** — *"raising microbial maintenance respiration while lowering the decomposition rate constant holds annual heterotrophic respiration at its calibrated value while shifting its seasonal distribution later, because maintenance scales with temperature and decomposition with substrate; refuted if the autumn excess does not fall while the annual total stays in band"*. The intervention still belongs in the row, in the parameters column where it is checkable. Compression is not the excuse: a cell too small for the hypothesis means the hypothesis goes in the section prose and the cell cites it.

**THE LEDGER CARRIES AN EXAMINED-MECHANISM COLUMN, LINKING IT TO THE PARAMETER REFERENCE** (PI, 2026-09-09). The two tables are the same investigation indexed two ways, cycle-by-cycle and parameter-by-parameter, and with nothing joining them a reader who wants to know which cycle tested a given parameter, or which mechanism a given cycle was probing, has to reconstruct the join by hand. One column of mechanism names per ledger row, drawn from the same vocabulary the mechanism section and the parameter reference use, makes both directions readable and makes an untested mechanism visible as a name appearing in one table and not the other.

**The PARAMETER REFERENCE table.** Every parameter the report names, in one place. **This is the table the next round's parameter list is built from**, which is why the source location and mechanism columns are not optional: a name plus a number cannot be re-judged a round later, and "verified in the source" is what separates a mechanism from a guess.

```markdown
| Parameter | What it is (units) | Where it acts in the source (`file:line`) | Mechanism it affects | Baseline | Range tested | Role in the outcome, and its status now |
|---|---|---|---|---|---|---|
| **GRDM** | seed carbon mass at planting (gC) | `PlantInfoMod.F90:###` | sizes the seedling that bootstraps the canopy | 1e-4 | 1e-3 to 5e-3 | dominant establishment lever; CALIBRATED in R2, DROPPED in R3's prune |
```

The status column carries the cross-round half: calibrated in round N / refuted with mechanism / baked into the base / never present / still `provisional:` on bounds. That is the column that stops the next round re-proposing a refuted lever, and it is filled from step 2 above.

**Arc the round by lever CLASS, not only by lever.** Each cycle's rethink recorded which class it exhausted (item 4 above), so the round report can state what the campaign has ruled out at the level the next round's parameter list actually needs. Several cycles refuting several parameters of one class is ONE refutation, and reporting it as several overstates what the round covered while hiding the class that was never tried — which is exactly the input item 9 of `calibration-discipline` wants for the next-round parameter add/remove.

It carries everything item 9 of `calibration-discipline` requires, above all the **next-round work
plan** (parameter add/remove, bounds recenter, base update, residual split). That item exists because
a round summary without one is the most common omission in this whole workflow.

> Distinct from `summarize-calibration-round`; the routing note at the top of this file draws the line.

### Canonical artifacts live in `phase_results/{stem}/`, and reports CITE them

This is what keeps the three layers from drifting apart:

- **Every canonical result of a PHASE — figure, its producing `.py`, its caption, its data — lives
  in the `phase_results/{stem}/` of the phase that produced it**, never in the report folder. A
  report-native **synthesis** figure, one that belongs to no single phase (a cross-cycle arc in a
  round report, say), is the documented exception and stays canonical in the report folder as
  `make_report_figures.py` — see §3, which owns that distinction.
- **A report embeds the rendered PNG and cites the canonical script**; it does not copy the `.py`.
- **A figure needs changing? Edit the script in `phase_results/{stem}/` and regenerate it there**,
  then re-copy the PNG. Never edit a copy next to the report, and never hand-patch a rendered figure:
  that is how a report ends up with a figure its cited script cannot reproduce.
- The one exception stays the deliberate **graduated figure** (below), a frozen public snapshot.

Two failures this prevents, both observed: a cycle report whose only figure showed **one** of three
scored targets, so a reader could not see that the tested variants also pushed the other two out of
band; and the same figure drawing a flat line at the multi-year observed **mean** in place of the
measured per-year series, which hides both the year-to-year spread and the years with no measurement
at all. When the observation is a measured series, plot it as one — points, spread, and gaps left as
gaps.

## Recipe

### 1. Gather citation-backed facts FIRST (before writing a word)

A report is only as good as its facts. For a topic spread across many logs, **fan out a subagent** to
extract a fact-sheet with **exact numbers + `file:line`/section** and to **flag contradictions** between
logs (superseded conclusions, unit mismatches, count discrepancies):

```
Agent (Explore): "Read logs L1..Ln. Extract a citation-backed fact sheet under headings
A..H. For every number/mechanism/equation give the exact value + file:line. Flag any
contradiction between logs and name the primary source. Read-only."
```

**For a ROUND report the fact-gathering opens one more source: that round's offline state file**, `use_cases/<Case>/memory/workflow_state_offline_r{NN}.json`. Its `evidence.diagnoses[] / .hypotheses[] / .experiments[]` carry a `one_line` per finding written when the finding was fresh, and `decisions[]` carries each finding as it was established. That is the reasoning chain in machine-readable form, and it is the one source that has not been through a layer of synthesis. See the ROUND report section for the measured reason this is not optional.

Then **reconcile the contradictions in the report** — don't silently pick one. (Worked example — the
demo-branch R5 mass-balance report: the pass surfaced a per-patch-vs-per-m² `num_plant` unit mismatch, a
superseded dropout %, and a stale "the fix is Option A" framing — all resolved in the report.)

### 2. Draft to the skeleton, applying the discipline

Lead each section with the plain finding; support with the mechanism; cite the evidence inline. Keep
**pending results as visible placeholders** ("final recovery rate appended when the chains finish"), and
**update the report when they land** — a report is a living document until the work closes.

### 3. Figures — `figures > tables > words`

Make figures for the load-bearing claims (`<auto-memory>/feedback_figures_over_tables_over_words`); build
them with the **`plotting`** skill (readable fonts, no overlap, **verify by viewing the PNG**). Embed each
with a **caption that states its takeaway**, and add a **"how to read this"** for complex figures (multi-
series, dotted reference lines, log axes).

**ONE canonical script per figure — never two copies** (`<auto-memory>/feedback_plot_scripts_canonical_in_phase_results`).
Keeping the same `.py` in two folders is the #1 cause of script-vs-figure drift: edit one copy and the
other silently goes stale (a Phase-6 folder re-carrying a Phase-5 script; a report duplicating a
`phase_results` script). So:
- A figure that **originates in a phase log** — its script is canonical in `phase_results/{stem}/`. **Edit
  it there and regenerate in-place** (the script writes to its own folder via `HERE=Path(__file__).parent`),
  then copy only the **rendered PNG** into the report and **cross-reference** the canonical script in
  Provenance. Do NOT duplicate the `.py` into the report folder.
- A figure the **report generates fresh** (a synthesis figure not tied to one phase) — its script
  (`make_report_figures.py`) is canonical **in the report folder**.
One script, one home; everywhere else references it or copies only the PNG. (A deliberate *graduation* of a
cleared-for-public figure is the one allowed copy — a frozen snapshot, below.)

**EVERY FIGURE IS DISCUSSED IN THE PROSE, BY NUMBER, IN THE SECTION THAT EMBEDS IT** (PI, 2026-09-09). An embedded figure nobody discusses is decoration: the reader cannot tell what they were meant to see, and the claim it supports is left to be inferred from the picture. Three parts, and the third is the one that gets skipped:

- **a body paragraph that names it as "Figure N"** and says what it shows about the argument this section is making. Not a restatement of the caption.
- **a caption whose FIRST SENTENCE is the finding**, not the axes. "Peak respiration arrives 15 days late in every year of the record" states a finding; "monthly R_eco, observed and simulated" states a subject.
- **anything identified ON the figure is identified IN WORDS.** A case id, a run label, a highlighted subset or a coloured group means nothing to a reader until the prose says what it is and why it is on this figure rather than another one. Measured 2026-09-09: a round report embedded and captioned its Figure 1 and mentioned it in no paragraph, while three later figures drew labelled case ids that appear nowhere in the text.

**Figures live in the section that ARGUES with them, never in the executive summary** (PI, 2026-09-09). The summary is read before the reader has the context to judge a figure, so a figure there is asserted rather than argued, and its section is left describing evidence that appeared ten paragraphs earlier. Place each one beside the table or the paragraph it draws; a section that runs table, figure, table, figure reads as one argument, and the summary can point forward to a figure by number without carrying it.

**TABLES ARE NUMBERED Table 1, Table 2, ..., NEVER LETTERED** (PI, 2026-09-09). "Table A" and "Table B" are this skill's internal names for the two required round-report tables, and they are not labels to put in a report: a lettered table reads as a draft. Number them in order of appearance and refer to them by number throughout, including from other sections and from the executive summary. `tools/check_report_conformance.py` errors on a lettered table label in report prose.

**Empty the image ALT text when you write a bold caption paragraph.** Embed as `![](figN.png)` (empty
alt) followed by a `**Figure N. <caption>**` paragraph — NOT `![Figure N](figN.png)`. Pandoc's
`implicit_figures` turns the alt text into a `<figcaption>`, so a "Figure N" alt text **plus** your bold
caption renders the label twice ("Figure 1: Figure 1"). Put the caption only in the bold paragraph; leave
the alt text empty. Enforced by `python3 tools/check_report_figures.py <report.md>` (run it before
rendering; it flags any `![Figure ...](...)` alt text).

### 3b. Skeptical-reviewer pass — before you ship, not after

Read the draft as a hostile but fair Reviewer 2 and **write down the two or three objections they
would raise**: an overstated generality, an alternative explanation, a missing control, an unsupported
leap, a number without an uncertainty. Fix or explicitly acknowledge each one.

**Test the comparison your headline rests on.** A report's central inference is usually a contrast
("A is displaced and B is not"), and a contrast that has never been tested is an impression. On
EcoSIM_Lusignan the carbon-versus-water contrast that justified the entire parameter list turned out
to sit at p = 0.087 — the right sign, not significant — and nothing in the drafting process had asked.

Full checklist: `manuscript-writing-style` §"Self-check before finalizing a section".

### 4. Place it + render

```
use_cases/{Model}_{Case}/reports/<YYYYMMDDx>_<topic>/            # timestamp-first, same-day letter REQUIRED
  ├── <topic>_report.md          # the synthesis report  (or NOTES.md for a single graduated figure)
  ├── *.png                      # embedded figures (PNGs copied in; phase figures reference their canonical script)
  └── make_report_figures.py     # canonical ONLY for report-native (fresh) figures
```
`reports/` is the **synthesis layer** — a report here distills the **key results from the logs** for a
reader, cross-referencing (not duplicating) the `memory/*_logs/` and `phase_results/{stem}/` it rests on.

**Naming — timestamp-first `{YYYYMMDDx}_{topic}/`, the same-day letter REQUIRED.** `x` is a sequential
letter (`a`, `b`, `c`, …) for reports written the same day — use the **next free** one (check existing
`reports/{date}*`); the `topic` carries any `R<round>` tag, e.g. `20260709b_R5_massbalance_resolution`.
Past `z` (27th+ same-day), keep `z` and append a second letter: `za, zb, …, zz` — sort-stable
(`z_` < `za`); never `aa` (it sorts before `b`). Same overflow rule as logs (`CLAUDE.md` §Session Logging).
The letter is **mandatory, not optional**: several reports a day is normal (per-cycle summaries plus a
round summary), and without it `ls reports/` cannot show creation order — a bare `{date}_{topic}` sorts
only by topic string, which is not chronological. The `.gitignore` tracks **any letter-containing
`reports/*` folder** and ignores only the pure-numeric `YYYYMMDD_HHMMSS` auto session/presentation dirs +
heavy media — so a curated `{date}x_{topic}/` folder is version-controlled + **public-synced**. Render a
shareable PDF with the **`markdown-to-pdf`** skill.

**Graduating a single figure (not a full report).** `reports/` is also the home for a **graduated durable
figure** — a headline result cleared for public that doesn't need a full narrative. Drop the figure `*.png`
+ its exact producing `*.py` + a `NOTES.md` (what it shows / key finding / why durable / provenance: source
round, case set, the `phase_results/{stem}/` it came from, the calibration log + ana_log) into a
`{YYYYMMDDx}_{topic}/` folder (same-day letter required) — same tracked + public-synced layer, and copying
the producing `.py` here IS allowed (a deliberate frozen public snapshot, the one exception to "one
canonical script"). Graduate **only cleared-for-public**
artifacts (embargoed results stay in gitignored `phase_results/`).

## Footguns

- **No author line** — a report whose header omits `**Author:** Jing Tao with A2MC` reads as orphaned: the
  reader cannot tell who produced it. Every report header carries it (structure step 1). No host suffix.
- **Undefined shorthand** — an internal codename with no definition is the #1 report failure; a reader
  bounces off it. Define or avoid.
- **A glossary block, at all** — removed from this skill 2026-08-24 (Structure step 2). It
  wastes the first page on terms the actual reader coined, and it licenses undefined jargon
  in the body ("it's in the key"). Define inline on first use; use **Outline** for navigation
  if the report is long enough to need it.
- **A figure-less wall of text** — if a claim is quantitative, it probably wants a figure or table. Don't
  bury the finding in prose.
- **Unverified figures** — a legend on top of the data undercuts the claim; view every PNG (`plotting`).
- **Duplicated figure caption** — `![Figure N](fig.png)` alt text + a `**Figure N.**` caption paragraph
  renders the label twice under pandoc (`implicit_figures`). Use empty alt `![](fig.png)`; run
  `tools/check_report_figures.py`.
- **Silently resolving a cross-log contradiction** — flag it and say which source you trust and why; a
  reader who later finds the other log needs to know it was superseded.
- **Stale placeholders** — a "TBD" left in after the result landed. Update the report when the run closes.
- **Duplicating a companion doc** — cross-reference `summarize-calibration-round` / an ana_log rather than
  restating it; keep each report's boundary clear. **This applies to NARRATIVE, never to a mechanism.**
  A finding about how the system works is carried, with its numbers and citations, at every level that
  claims to summarise the work; only the blow-by-blow of how it was reached stays in the document below.
- **Cross-referencing a mechanism instead of carrying it** — the failure the rule above guards. Measured
  2026-09-05: a round report described a two-solute trade-off correctly in four places and never named
  the state variable that causes it, the fixed source ratio that creates it, or the saturation asymmetry
  that splits it. All of it sat in that round's first Phase-3 diagnosis with source citations, and in the
  round's offline state file. The report passed every conformance check at every commit, because the
  checks asked whether structures were present and the science belonged to no structure. If a reader of
  your report alone cannot say WHY the round's central result happens, the mechanism did not travel.

## Cross-references

- **`calibration-goal`** — the run-to-convergence DRIVER dispatches this skill as part of the round CLOSE. `resolve_next_action()` returns `close("round_close")` when a round ends, and the driver runs the three steps in order: `summarize-calibration-round` -> `compare-calibration-rounds` -> `write-report`. The close happens BEFORE the Phase-6 human gate, so the PI routes the round with these deliverables in hand.

- Discipline: `<auto-memory>/feedback_report_writing_self_contained`, `feedback_figures_over_tables_over_words`,
  `feedback_logs_cite_explicit_evidence` (name the figure/table/statistic/data file behind every claim — in
  reports as in logs).
- Pieces: `plotting` (figures — the A2MC ensemble figure template), `markdown-to-pdf` (render to PDF/docx),
  `scientific-analysis` (the investigation→figure→ana_log that often feeds a report).
- **Reciprocal skills** — `manuscript-writing-style`: this skill borrows its Rigor / Transparency /
  Self-check layer for report prose, and it points back here for non-journal reports. Register and
  section scaffold stay its own.
- **`summarize-calibration-round`** — not a rival, a SUPPLIER. It produces the round's
  standardized figures and tables (whole-ensemble graphs, screening evaluation, Morris μ*),
  and the ROUND report this skill defines **cites** them rather than regenerating them. The
  routing note at the top draws the boundary; that skill's own layer section draws it from
  the other side. Do not restate its content in a report — cite it.
- Worked example (every step above): the demo-branch R5 mass-balance resolution report
  (`massbalance_resolution_report.md` + `make_report_figures.py`) — it lives on the demo branch's reports
  layer, not on `main` (referenced by name, not a live path, so main stays checker-clean).
- Worked example (Outline, no glossary — the shape now required of every report):
  `use_cases/PFLOTRAN_miniLEO/reports/20260814a_MiniLEO_Full_Case_Report_And_Coupling_Roadmap/A2MC-PFLOTRAN_miniLEO_full_report.md`
  — a long (8-section) report back to a team that already shares its vocabulary; Outline for
  navigation, terms defined inline.

## Notes

- **Branch fit:** generic report-writing conventions — applies on any branch and any model configuration.

## Changelog

- 2026-09-09: **FIVE WRITING RULES, from a PI critique of a round report that passed every checker.** (1) The **register** bullet, added to the discipline: "zero-context reader" was being read as "simplify the science", and it produced an executive summary describing eddy-covariance fluxes as "how much carbon it takes up, how much it breathes out" and answering its own research question with "yes, comfortably". The zero-context bullet now says explicitly that it never governs the register. (2) **Every figure is discussed by number**, its caption states the finding, and anything labelled on it is identified in words: the report embedded a Figure 1 no paragraph mentioned, and drew case ids that appear nowhere in the text. (3) **Tables are numbered, never lettered** — with the skill's own "Table A"/"Table B" labels renamed to the CYCLE LEDGER and PARAMETER REFERENCE tables, since a skill that names them by letter teaches the label it forbids; `check_report_conformance.py` now errors on a lettered label in report prose, dated from 2026-09-09 so existing reports keep theirs rather than leaving the checker permanently red. (4) The ledger's **hypotheses must be complete scientific hypotheses** (proposition, mechanism, predicted consequence, falsification bar) rather than intervention labels like "SPOSC up, the direction cycle 0 did not try", and the ledger gains an **examined-mechanism column** joining it to the parameter reference. (5) **Figures live in the section that argues with them, never in the executive summary**, where a figure is asserted before the reader can judge it; (6) **Section 1 states the outcome quantitatively including the reopen conditions, section 2 establishes the problem with a figure**, and the Structure section now says the outline is a story to build rather than boxes to fill. No `description` change: the trigger is unchanged, only what the skill requires once fired.

- 2026-09-09 (later, 3): **Says where a report's OWN script lives**, beside the nesting diagram: a report generating NEW artifacts that belong to no phase stem keeps that script with itself. The canonical-script rule governs a phase's figure scripts and bites only when a report copies an existing stem's script and edits it there. PI correction, after the rule was read too broadly.

- 2026-09-09 (later, 2): **Section 5 cross-references the never-reimplement rule.** The section told the author which criterion to rank on and not to compute it with the round's own function; a report that recomputes its criterion can disagree with every recorded number. One bullet. No `description` change.

- 2026-09-09 (later): **Section 5's ranking rule CORRECTED and the bullets trimmed** (PI). It said to rank on the criterion `targets.yaml` scores, which is the wrong answer where the scored criterion already passes for every configuration: ranking on it returns what the round spent its cycles rejecting. Now: rank on the criterion the round STEERED BY, gated as the round gated it. Five bullets to four, measured episode dropped as too case-specific.

- 2026-09-09 (later): **Section 5 must DELIVER the round's product: the ranked SET of calibrated parameterizations, with a link and a PROVENANCE table.** PI-directed, and the PI's framing is the one adopted: *"the whole calibration work is to calibrate parameters and provide parameterizations that produce top 10 best cases, if not the best one"*. Every artefact in the round close described the round's REASONING and none handed over the RESULT as a usable set. The cause was not one skill: `phase6-refinement`'s deliverable contract is singular throughout ("the parameter values ... its final value") and top-N ranking lived only in Phase 2 as a mid-round analysis step that nothing carried into the close. **Measured:** one round's adopted configuration was worse on the criterion its own `targets.yaml` scores than ten sampled configurations, and better than all 3,880 on a seasonal criterion the campaign never scored; the close reported the recommendation and concealed both halves, and its best-scoring configurations were filed as "alternates" beside it. The section now requires the top-N table ranked on the SCORED criterion, any second criterion in the same table with the disagreement stated, a provenance row per entry naming its origin and where it is discussed (including, plainly, the entries never individually examined), a link to the `{stem}_FINAL_CONFIGURATION/` bundle, and the cumulative figure with the set drawn on it. Paired with `phase6-refinement` element 1. No `description` change.

- 2026-09-05 (later, 3): **`compare-calibration-rounds` added as the FIFTH required skill, and required from the FIRST round.** PI question: is there anything to compare at R1? Only Deliverable 2, the cross-round figures, is not applicable there; the parameter ledger, the model-evolution record and the mechanism ledger all have content at R1, and the one-column ledger a first round writes is the baseline every later round is checked against. Skipping it moves the reconstruction work to Round 2, which is where a round summary was measured re-proposing two already-refuted parameters. That skill gains a section stating what a first round produces, deliverable by deliverable.
- 2026-09-05 (later, 2): **Four skills are REQUIRED for a round report and must be named in it, enforced as an ERROR.** PI-directed: `summarize-calibration-round`, `write-report`, `calibration-goal`, `calibration-discipline` (a fifth, `compare-calibration-rounds`, was added the same day; see the entry above). A round report is the OUTPUT of that pipeline, not a document someone sits down and writes, and one assembled from whatever was on disk is how a round report lost its own central mechanism while passing every check. `tools/check_report_conformance.py` now ERRORS when a name is missing, with the remedy stated as run-the-skill-and-redo rather than add-the-name. `tools/check_skill_claims.py` is extended to reports, but **only reports being ADDED** (`--diff-filter=A`): a report's capability section describes the session that WROTE it, so checking edits would fail every correct report in a later session and pressure the agent into stripping true claims, the exact inversion that check exists to prevent. `compare-calibration-rounds` is required by this skill's step 2 and is deliberately NOT in the enforced list, pending a PI call. Tests: one per required skill, each dropping exactly one name, plus an unbackticked-name case, because the two checkers must agree that a claim is a backticked token. `description` untouched; no trigger change.

- 2026-09-05 (later): **The ROUND report gets a CANONICAL SEVEN-SECTION OUTLINE, and the mechanism moves inside section 4.** PI-directed, on reading a round report whose contents list had grown to thirteen top-level headings with titles like *"What was being calibrated, for a reader with no context"* and *"The design, and what the round actually ran"* — a heading's purpose used as its name. The outline had accreted one heading per requirement as requirements were added, and nobody had ever looked at the list as a list. Two changes. **(1) Seven named sections**, each absorbing the headings that answer one question: the calibration design; screening results and sensitivity; **mechanism and hypothesis testing**; improvement and gained knowledge; open questions and next-round plan; A2MC self-check and provenance. **(2) The cycle ledger, the arc, the mechanism and the parameter reference are ONE section**, because they are one argument — what was hypothesised, what was tested, what came back, what the system is therefore known to do. Scattered across four top-level headings the mechanism sat between two tables looking like a third table, which is close to how it went missing in the first place. The checker needed one fix in the same pass: its mechanism-citation rule took the FIRST matching heading, which under the new outline is the section heading whose own intro carries no numbers, so it reported "cites nothing" on a correctly cited report; it now scans every matching heading and passes if any body cites. `description` untouched; no trigger change.
- 2026-09-05: **The ROUND report now requires a MECHANISM section, and must read the round's offline state file.** PI-directed, from a question about why a round report skipped the science its own cycle reports carried. Measured decay of one round's central mechanism across the synthesis chain: named throughout the Phase-3 diagnosis with `file:line` citations, twenty times in the first cycle report, once in the second, **zero times in the round report**, while the round's whole finding was that this variable split two solutes released from one source in a fixed ratio. Four causes, all addressed here. (1) The obligation already existed, in the ROUND section's opening sentence about the first Phase-3 diagnosis, as the **only** content requirement among five structural ones, so it was also the only one no checker could see; it now has a named section. (2) "Synthesize, do not re-narrate" was read as licensing the omission, and the four things that paragraph lists to carry are all process-shaped; a blockquote now states that the instruction governs narrative and never science. (3) Neither required table is indexed by mechanism: Table B holds one cell per parameter, so a relation between two parameters, a variable that is neither sampled nor scored, and the finding that the parameter list itself was wrong all have no row by construction, and their absence leaves no visible hole. (4) The report path never opened `workflow_state_offline_r{NN}.json`, where **every one of the eight missing quantities was already sitting** in one diagnosis `one_line` beside 156 recorded decisions; `compare-calibration-rounds` already read that file for its `decisions`, so this aligns the two. **Reconciled in the same pass (step 5):** the recipe's fact-gathering step named only logs and cycle reports, and the "duplicating a companion doc" footgun, read broadly, licensed exactly this omission; both are amended, and a footgun now names the failure directly. **Enforcement, in the same commit:** `tools/check_report_conformance.py` gains the mechanism check (heading, plus a second warning when the section cites nothing checkable) and its four **word-match** round checks are anchored to headings, because `sensitivit`, `next-round`, `model evolution` and `open-question` as bare substrings were checks that could not fail; proven on a negative-control fixture that passes all four old checks and trips all five new ones. **No trigger change:** `description` is untouched.

- 2026-08-24 (later): **The ROUND report must carry a sensitivity figure and discussion, whatever the sampling method.** PI-directed. Nothing had required it, and a round whose Saltelli estimator did not converge shipped a round summary with no sensitivity figure at all, while the same ensemble held 2,374 already-run controlled single-parameter experiments that nobody had extracted. A failed estimator is a reason to change instrument, not to drop the section, so the report now names `summarize-calibration-round` guarantee 3's fallback ladder and requires the rung to be stated. It also requires viability to be covered as its own dimension where deaths are non-trivial, since a sensitivity section computed on survivors alone discards most of what a round with an 81 percent death rate measured.
- 2026-08-24: **Three PI-directed changes to the report contract.** (1) **The `## Reader's key` / glossary block is REMOVED**, reversing the 2026-08-18 entry below that had made it one of two navigation aids. In practice it front-loaded definitions the actual readers already knew and licensed undefined jargon in the body on the excuse that a key existed; the obligation it stood for is unchanged and now discharged **inline on first use**. Structure step 2 is Outline only, and the discipline bullets, the footgun and the worked-example line were reconciled in the same pass. (2) **The ROUND report now names two skills that RUN BEFORE it**, `summarize-calibration-round` then `compare-calibration-rounds`, as steps rather than options. The second is the load-bearing one: the round report must carry what earlier rounds established, and all four next-round-plan bullets are cross-round questions. Signal: one round summary proposed adding two parameters that earlier rounds had already tested and refuted with named mechanisms, and both survived every checker because nothing in the round-close path opens a prior round. (3) **The ROUND report requires two tables** — a cycle ledger (question and bar, parameters and values, result per scored target, verdict) and a parameter reference (what it is, `file:line`, mechanism, baseline, range, role **and cross-round status**). Both were written by hand in the R1 and R2 round summaries and are now contract; the status column is what stops the next round re-proposing a refuted lever.


- 2026-08-23 (later): **CYCLE item 4 also carries the rethink's DIRECTION audit**, following the sixth question added to `phase6-refinement` Step 4 the same day (PI-directed). A report that lists refuted levers without saying which DIRECTION each was refuted in, and from a base missing its target on which SIDE, tells a reader the round is more exhausted than it is — which is the same overstatement the lever-CLASS arc was added to prevent, one level down.
- 2026-08-23: **The CYCLE report's item 4 carries the RETHINK, and the ROUND report arcs by lever CLASS.** PI-prompted, paired with the rethink protocol added to `phase6-refinement` Step 4 the same day. Item 4 previously ended at "the routing (rethink 6→3, redesign 6→0, converge)", which treats the route as a label — the same shape the Phase-6 skill had before it gained a protocol, and the reason a reader could not distinguish a redirected campaign from a stalled one, since both present as a list of refutations. It now requires the class verdict and the NEW PATHWAYS with their falsifiers, and says to DRAW them from the Phase-6 log rather than re-derive: the protocol's item 1 produces that synthesis and carries a write-once clause, so deriving it twice would guarantee the copies drift. The ROUND report gains the reciprocal at round scale: arc by lever CLASS, because several cycles refuting several parameters of one class is one refutation, and reporting it as several overstates coverage while hiding the untried class — which is the input the next-round parameter add/remove needs.


- 2026-08-22: **Names the CYCLE report and the ROUND report as structural deliverables, with a stated scope.** PI-directed, on reading a cycle report that under-covered the work behind it. Three requirements the file did not carry: a cycle report must walk the **whole inner Phase-3<->4 loop iteration by iteration** (what each skip-test asked and answered) rather than only the surviving hypothesis; it must name **every hypothesis with its falsification bar, the variants that tested it and their job ids**; and it must report results **per variant per SCORED target against the measurements**, not one composite or one target of several. The round report synthesizes the CYCLE reports rather than re-deriving from raw logs. Evidence: across one campaign's three rounds, 46 phase-3/4 logs sit at `iter01` and 4 at `iter02` against a cap of 10, so "cover the iteration" was silently covering all there was and the under-use of the free loop was invisible in every report; and one cycle report shipped with a single figure showing one of three scored targets, drawing a flat line at the multi-year observed mean in place of the measured per-year series. Also states that canonical phase artifacts live in `phase_results/{stem}/` and that a figure needing change is edited and regenerated THERE. Reconciled two contradictions the edit introduced: §3 already carves out the report-native synthesis figure as canonical in the report folder, and the routing note's "not this skill" line needed to distinguish the standardized `summarize-calibration-round` deliverable from this skill's round report.

- 2026-08-18: **Added the no-hard-wrap rule** beside the no-em-dash rule, and gave both a memory
  (`feedback_prose_no_em_dash_no_hard_wrap`). The em-dash rule had lived ONLY in this skill plus two
  reminders in `calibration-discipline`, and the memory that referenced it pointed at a
  `~/.claude/CLAUDE.md` section that does not exist on Perlmutter — so it was invisible to every dev
  log, ana log, calibration log and commit body, which are written outside this skill. The wrap rule
  is not only taste: markdown joins consecutive lines, so a hard-wrapped metadata block collapses in
  every renderer.
- 2026-08-18: **Structure step 2 splits into "Outline" and "Reader's key / glossary"** — two
  different navigation aids that the old single "Reader's key / glossary" slot conflated: a
  table of contents (valuable for any long report) versus jargon-defining (valuable only for a
  reader outside the immediate group). Found writing the PFLOTRAN miniLEO full case report back
  to a team that already shares its vocabulary: the PI caught it directly ("please replace
  '## Reader's key' with an outline... everyone already knows these terms") and asked for the
  distinction to become a standing convention rather than a one-off edit. Adds a matching
  footgun (glossarizing an audience that already knows the jargon) and a worked-example
  cross-reference. Also clarified the "Zero-context reader" discipline bullet to scope explicitly
  to A2MC-internal codenames, not a standing team's own domain vocabulary, so it does not read as
  contradicting the new Outline-only option. Drafted and PI-reviewed on
  `A2MC-adapter-kit-PFLOTRAN` (`memory/dev_logs_adapterkitpflotran/20260815a_Handoff_To_AdapterKit_Write_Report_Outline_Vs_Readers_Key.md`),
  landed here per that branch's additive-only rule (generic `.claude/skills/` changes are
  `adapter-kit`'s to make). **Same-day follow-up (PI):** the description's "Write a **general**
  ... report" and "this skill is the **general**, topic-agnostic integrated report" read as
  license for a shallow or non-comprehensive report; both reworded to **comprehensive**. The
  word was scoping this skill against `summarize-calibration-round`'s FIXED deliverable (not a
  rigor bar), but the skill's actual content — cite every calibration phase log/result behind a
  claim, finding→mechanism→evidence sentences, the skeptical-reviewer pass — already demands
  comprehensive, evidence-cited, high scientific quality, so the wording now says so directly
  instead of relying on a reader inferring it from "topic-agnostic."
- 2026-08-17: **Borrows `manuscript-writing-style`'s rigor layer instead of only routing away from it.**
  It was referenced three times, every one as "NOT this skill" / "don't overlap", so its Rigor,
  Transparency and Self-check sections — which are register-INDEPENDENT — were never applied to a
  report. Measured before changing: this skill contained 0 mentions of uncertainty, inference,
  fabrication or limitations against 4/5/3/5 there. Adds three discipline bullets (label an
  unverified claim; every quantitative claim carries its uncertainty; keep data / model inference /
  interpretation distinct) and a **skeptical-reviewer pass** step that requires testing the contrast
  the headline rests on. Evidence: the EcoSIM_Lusignan pre-R1 report quoted a phase shift of "+13
  days" whose year-to-year SD was 16 days and which was negative in 2 of 11 years, and justified its
  whole parameter list on a carbon-versus-water contrast never tested (it sits at p = 0.087). The PI
  found both by looking at a figure. Declares reciprocity, so the pair is now enforced.
- 2026-07-19: **Author line now REQUIRED in the header** (structure step 1 + a footgun): every report
  opens with exactly `**Author:** Jing Tao with A2MC` (no host suffix). The `with A2MC` author is
  report-SPECIFIC (public-facing A2MC deliverables credit the framework); every other artifact — dev/ana
  logs, scripts, commits — keeps the `CLAUDE.md` `Jing Tao with Claude` convention unchanged. The R1 EcoSIM
  report set shipped without any author line, which prompted this rule.
- 2026-07-18: **Same-day letter overflow** past `z` — keep `z` as a prefix and append a second letter
  (`za, zb, …, zz`, sort-stable), never `aa` (sorts before `b`). Same rule for logs; `CLAUDE.md` §Session
  Logging is canonical and `tools/phase_logger.py::_offline_letter` auto-assigns it for offline stems.
- 2026-07-18: Two conventions from the EcoSIM R1 report set. (1) **One canonical script per figure** (FIGURES
  step 3): a phase figure's `.py` is canonical in `phase_results/{stem}/` (edit + regen there, copy only the
  PNG to the report, cross-reference the script); a report-native figure's script lives in the report folder;
  never two copies (memory `feedback_plot_scripts_canonical_in_phase_results`). (2) **Report folder same-day
  letter now REQUIRED** — `{YYYYMMDDx}_{topic}/`, not the previously-optional `[x]` — so `ls reports/` shows
  creation order when several reports land the same day.
- 2026-07-17: Added the **empty-image-alt-text** convention (FIGURES step 3 + a footgun): embed `![](fig.png)`
  + a bold `**Figure N.**` caption, never `![Figure N](...)`, else pandoc `implicit_figures` renders the label
  twice. New linter `tools/check_report_figures.py` enforces it. Generic (cross-branch handoff to main).

- 2026-07-16: Added the **no-em-dash rule** to the discipline (user preference): use commas / colons /
  parentheses / sentence splits instead; en dashes in numeric ranges are fine; applies to the rendered PDF too.
- 2026-07-16: Incorporated the demo `316092b` reports-layer parts (**minus** the promote-milestone
  retirement — main never had that skill): the **timestamp-first `{YYYYMMDD[x]}_{topic}/` folder convention**,
  the **synthesis-layer framing** (a report distills key results from the logs) + an optional
  **single-figure graduation** step (figure + producing `.py` + provenance `NOTES.md`), and the matching
  `.gitignore` switch (track any letter-containing `reports/*`; ignore only pure-numeric session dirs +
  media). Re-added the `feedback_logs_cite_explicit_evidence` cross-ref (+ ported that memory to main) and
  the full-path R5 worked example.
- 2026-07-09: Ported to `main` from demo `5ef9cc7` (v3.13) — distilled from the R5 mass-balance resolution
  report (demo branch): zero-context structure, subagent fact-gather + contradiction-reconcile pass, and the
  plotting/markdown-to-pdf pieces. The topic-agnostic complement to `summarize-calibration-round`. Added
  main's `modes:` block; dropped the demo-only `feedback_logs_cite_explicit_evidence` cross-ref.