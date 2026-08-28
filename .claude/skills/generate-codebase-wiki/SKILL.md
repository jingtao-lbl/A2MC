---
name: generate-codebase-wiki
visibility: public
category: kb-build
description: Produce a source-grounded codebase wiki for a model (FATES, ELM, EcoSim, ReSOM, or a new target) by fanning out parallel subagents that read actual source and cite (file:line) — the foundation every downstream A2MC artifact (RAG vector index, knowledge graph, calibration prompts) is built on. Use when the user asks to "generate/build a codebase wiki", "the deepwiki/cursor wiki is wrong — rewrite it", "audit the wiki against source", "bump the wiki to commit X", or "add model Y to A2MC" (wiki is step 1). Picks Workflow A (greenfield) vs B (audit-then-rewrite), enforces the fabrication/citation gates and commit-pinned output convention. Distilled from docs/a2mc_reference/codebase_wiki_generation_roadmap.md and the FATES/ELM/EcoSIM wiki dev logs.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [rag]
  summary: "Generate a source-grounded codebase wiki for any model; model-agnostic."
---

# Generate a Source-Grounded Codebase Wiki

Full procedure, universal-context templates, and per-subagent prompts live in
**`docs/a2mc_reference/codebase_wiki_generation_roadmap.md`** — read it before dispatching.
This skill is the decision + dispatch + verification runbook.

> **Why this is the foundation.** The wiki feeds the ChromaDB vector index, the knowledge
> graph, milestone metadata, and ultimately the calibration agent's prompts. *Nothing built
> on top can be more correct than the wiki.* A fabricated routine name propagates silently
> all the way to a calibration recommendation. Treat every claim as suspect until cited.

## Step 1 — choose the workflow

| Situation | Workflow | Why |
|---|---|---|
| New model, no prior wiki | **A — greenfield** | nothing to audit; write from source |
| Auto-generated (deepwiki/cursor) wiki exists but is fabricated | **A — greenfield** (abandon the old one) | fabrications hide fabrications; don't patch incrementally |
| Source-grounded wiki exists, commit bumped **within** an api epoch | **skip** | milestone covers sci drift via param-file sha (`docs/18`) |
| Checkout sits on an **in-flight experiment branch** (verification not yet passed) | **skip** | the branch may be abandoned or reworked; minting a pinned dir for a moving target is churn. Re-verify the few affected pages ad hoc with `git grep` |
| **Verified change LANDED in the working model** — an experiment branch merged to the fork's `main` after its paired verification passed (`model-evolution` step 5) | **C — targeted drift refresh** | the tree `A2MC_MODEL_PATH` resolves to has genuinely moved, so the wiki is now wrong about the model actually being run. Regenerate only the pages the diff invalidates; copy the rest forward (PI, 2026-08-14) |
| Source-grounded wiki exists, commit bumped **across** api epochs (e.g. api-31-0 → api-43-1) | **B — audit then rewrite** | catch semantic drift (inverted units, fabricated defaults) before re-canonizing |

**A vs B litmus:** if the existing wiki makes *semantic/behavioral* claims that can be
silently wrong (GDD thresholds, MPa↔mm unit inversions, formula direction), audit first
(B). If errors are merely *structural* (wrong filenames, off-by-N line numbers, nonexistent
dirs), greenfield (A) catches them without a separate audit pass.

### Workflow C — targeted drift refresh (when a VERIFIED change lands in the working model)

A full regeneration costs 100K–400K tokens *per subagent*. When the working model moves but the diff
is bounded, most pages are still correct — regenerate only the ones the diff actually invalidates.

**The wiki tracks the WORKING MODEL, not upstream releases.** Waiting for an api-epoch bump is the
wrong cadence: FATES milestones are rare and expensive, so a milestone-gated wiki stays stale for
months while the tree `A2MC_MODEL_PATH` resolves to has moved underneath it — and that tree is what
the agent reasons about. Fire on the *merge*, not the release: once an experiment branch has passed
its paired verification (`model-evolution` step 5) and merged to the fork's `main`, the change is
permanent in the model being run, and the wiki is now wrong about it. Before that merge the branch may
still be abandoned or reworked, which is why an in-flight branch is a **skip**.

**Do not select pages by "cites a changed file".** Core modules are cited nearly everywhere, so that
filter selects the whole wiki: measured 2026-08-14 on FATES `e027a40`→`a54120e3`, 14 changed files
selected **55 of 56 pages**. (Measured while that branch was still in flight — per the Step-1 table
that state is a **skip**; it is quoted here as the worked example of the selection arithmetic, which
is identical once the branch merges.) Select by whether a page's own citation lands in a changed
*hunk*:

```bash
git -C "$SRC" diff --name-only <pin>..<new>            # changed files
git -C "$SRC" diff -U0 <pin>..<new> -- <file>          # @@ hunk ranges in the NEW file
# then, per wiki page, compare its `File.F90:NNN` citations against those ranges
```

| Citation lands… | Meaning | Action |
|---|---|---|
| **inside** a changed hunk | the cited content itself changed | **regenerate** the page |
| only **after** a hunk | content intact, line number shifted | copy forward; re-anchor only if cheap |
| neither | untouched | copy forward |

On the measured example this reduced 56 pages to **6**. All of it is `git diff` against the index —
no filesystem traversal, so it is compliant on a shared filesystem
([[feedback_nersc_no_recursive_traversal]]).

**Write a NEW pinned directory, never edit in place.** `-<newcommit>/` gets the copied-forward pages
plus the regenerated ones. Editing pages inside `-<oldcommit>/` would make the directory name a lie,
which is the one thing the commit-pinned convention exists to prevent. Give `index.md` the "What
changed" section Step 5 already requires for a bump, and say explicitly which pages were regenerated
and which were carried over — a reader must be able to tell how much of the wiki was actually
re-verified against the new source. Then run **`validate-rag-chain`** as usual: copied-forward pages
have *not* been re-checked against the new tree, so the citation validator is what catches a page
whose lines shifted further than the hunk analysis predicted.

## Step 2 — stage inputs (read-only)

1. Clone or symlink the source checkout; **`git checkout` the exact commit** you're pinning.
2. Stage the parameter file (CDL/JSON/YAML) if the model has one.
3. Decide topics: **5–10, aligned to source subdirectories**, not editorial taxonomy — so
   "where is X implemented?" maps mechanically to a wiki file. A cross-cutting module goes
   in the topic where it conceptually lives (e.g. FATES `EDMainMod.F90` → core dynamics, not
   biogeochem). Promote a calibration-critical doc to its own topic (FATES
   `advanced/cnp_calibration_guide.md` is its own topic for this reason). **Size by source
   LINE COUNT, not file count** — see "Cost & footguns" below before finalizing the split.

## Step 3 — pilot 2 before fanning out all N

Dispatch **2 subagents on the highest-stakes topics first**, spot-check their output, then
fan out the rest. Skipping this is how "dispatched 10 in parallel and they all produced thin
output" happens. For a coupled pair (ELM+FATES), the topic documenting the **coupling
boundary contract** (ELM `core/`) is the highest-stakes pilot.

## Step 4 — dispatch the subagents (single message, non-overlapping scope)

One subagent per topic, all in **one message** so they run concurrently. Each subagent's
prompt MUST carry the universal-context block (≤15 bold-ordered bullets — longer and they
skim it) and these hard constraints:

- Read **actual source** via Grep/Read; cite **every** claim as `(path/Module.F90:NNN)`
  relative to source root. Use **this commit's** line numbers, never the prior wiki's.
- Cite filenames **verbatim from `ls`** (casing trap: `ELMFatesInterfaceMod.F90` vs
  `elmfates_interfaceMod.F90`).
- Output **150–500 lines per doc**; start with the standard header:
  ```markdown
  **Source pin:** <model> commit <HASH>
  **Scope:** <subsystem>
  **Last verified:** <YYYY-MM-DD>
  ```
- **Workflow B only:** anchor everything to the NEW source; run an explicit **regression
  check** that previously-corrected items weren't quietly rolled back (roadmap step B.6),
  and emit an audit report per topic before the rewrite.

## Step 5 — output convention

Write to a **commit-pinned directory**, never overwriting the old one:

```
docs/<model>-knowledge-base/<model>-codebase-wiki-<COMMIT>/
```

A future bump creates a parallel `-<newhash>/` folder (traceability + rollback; the RAG
loader is later pointed at it via the `rebuild-rag` Recipe-1 symlink). Write a top-level
`index.md`; for a bump, give it a "What changed" section; for an abandoned deepwiki, state
explicitly that it was abandoned and why.

## Step 6 — verify before committing

- **Fabrication spot-check:** sample 3–5 claims per topic — parameter defaults against the
  param file, routine names as real `subroutine`/`function` declarations, cited line ranges
  in-range, and `find` for any directory the wiki names. (Real failures seen: FATES
  `phen_a` claimed `100/100/0.01` vs actual `-68/638/-0.01`; EcoSIM cited
  `build_EcoSIM.sh`/`docker/` files that don't exist upstream.)
- **Header completeness:** `grep -L 'Source pin' docs/<model>-knowledge-base/<…>/*.md`
  must be empty.
- Commit in two commits for Workflow B (audit reports, then rewrite).
- Then run the **`validate-rag-chain`** skill (Step 1, wiki↔source) — it automates the
  citation/line/routine/module checks across the whole wiki and is the real gate before the
  wiki gets canonized.

## Cost & footguns

~30–60 min for Workflow A, ~60–90 min for B, ~2–3 h for a coupled pair; **100K–400K tokens
per subagent** (this dominates the API budget — scope topics by **source LINE COUNT, not
just file count** (a topic with few files can still be badly under-resourced if one file is
huge and equation-dense — flag any single file over ~2,500 lines as a mandatory split trigger
regardless of its topic's file count), split oversized subsystems into `_part1/_part2`).
Other traps: stale line numbers (subagent reads the prior wiki instead of new source), topic
boundaries cross-cutting a module so both under-document, **a named output/calibration
variable with no topic that owns it** (its producing equation sits in a large generic I/O
file, orphaned from every process topic — see the roadmap's "Output-registry extraction"
section), over-long universal context. The roadmap's "Common pitfalls" table is the full
list.

## Notes

- Proven examples: `20260410e` (Workflow A, ELM), `20260410d` (Workflow B, FATES audit),
  `20260424g` (Workflow A, EcoSIM new-model). Recipes A1/A2/B1/B2/B3 in the roadmap.
- This is **step 1** of the adapter-kit pipeline → then `rebuild-rag` (Recipe 2 registers
  the model) → `inject-knowledge`/curated YAML → `validate-rag-chain`.
- Branch note: codebase-wiki work is forward-dev — its natural home is `main`/adapter-kit.
  The api-31-0 wikis (`fates-codebase-wiki-e85d997`, `elm-codebase-wiki-60d9aad`) on
  a version-pinned manuscript branch are the reproducibility anchor; regenerate them only
  with explicit reason.

## Changelog

- 2026-08-14: **Added Workflow C — targeted drift refresh**, plus two new Step-1 rows (skip for an
  in-flight experiment branch; Workflow C once a verified change lands in the working model). Signal:
  NERSC's traversal
  prohibition made the wiki load-bearing for compliance, not just quality — it is the in-repo way to
  answer a source question without walking a checkout on a shared filesystem
  ([[feedback_nersc_no_recursive_traversal]]) — which immediately raised "what if the wiki has
  drifted?". Measured on the api-43 checkout: 14 changed files, and the obvious page-selection filter
  ("cites a changed file") selected **55 of 56** pages because core modules are cited everywhere,
  whereas selecting on whether a citation lands **inside a changed hunk** selected **6**. Workflow C
  encodes that discriminator, the copy-forward-into-a-NEW-pinned-directory rule (editing in place would
  make the commit suffix a lie), the "what was regenerated vs carried over" disclosure, and the
  `validate-rag-chain` follow-up that catches carried-over pages whose lines shifted further than the
  hunk analysis predicted. **Trigger decision (PI):** fire when a **verified change lands in the
  working model** — an experiment branch merging to the fork's `main` after paired verification — NOT
  on an api-epoch milestone. FATES milestones are rare and expensive, so milestone-gating would leave
  the wiki stale for months against the tree `A2MC_MODEL_PATH` actually resolves to, which is the tree
  the agent reasons about. An in-flight branch stays a **skip**: it may still be reworked or abandoned.
- 2026-08-12: **Topic sizing now weighted by source LINE COUNT, not just file count** (Step 2 +
  "Cost & footguns"), plus a new named-output/calibration-variable trap. EcoSIM's `microbial_bgc`
  topic (9 files, 9,811 lines, including the 4,393-line `MicBGCFGMod.F90`) got the same 2-doc
  budget as much smaller topics — a calibration-critical mechanism (the `RCCZ` mortality-recycling
  equation, at line 4132 of 4393) and the site's own calibration target (`CO2_SEMIS_FLX_col`,
  defined in a different topic entirely, `io_and_forcing`) were both never documented, discovered
  only when a same-day source investigation went looking for them directly. Root cause + fix in
  `memory/dev_logs_adapterkit/20260812b_*`; roadmap doc gets the matching detail (topic-decomposition
  bullet + pitfalls-table row + an "Output-registry extraction" extension covering models with no
  CDL at all, e.g. PFLOTRAN's text/deck-based output).
- 2026-06-17: Initial version — distilled from docs/a2mc_reference/codebase_wiki_generation_roadmap.md (Workflow A/B; FATES/ELM/EcoSIM proven examples).
