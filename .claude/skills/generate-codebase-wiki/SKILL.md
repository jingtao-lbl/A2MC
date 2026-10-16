---
name: generate-codebase-wiki
visibility: public
category: kb-build
description: Produce a source-grounded codebase wiki for a model (FATES, ELM, EcoSim, ReSOM, or a new target) by fanning out parallel subagents that read actual source and cite (file:line) — the foundation every downstream A2MC artifact (RAG vector index, knowledge graph, calibration prompts) is built on. Use when the user asks to "generate/build a codebase wiki", "the deepwiki/cursor wiki is wrong — rewrite it", "audit the wiki against source", "bump the wiki to commit X", "patch the knowledge base for a fix on top of a round's base binary", or "add model Y to A2MC" (wiki is step 1). Picks Workflow A (greenfield), B (audit-then-rewrite), C (drift refresh for a new base) or P (patch in place), enforces the fabrication/citation gates and commit-pinned output convention. Distilled from docs/a2mc_reference/codebase_wiki_generation_roadmap.md and the FATES/ELM/EcoSIM wiki dev logs.
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
| **Verified change LANDED on top of a round's base binary** — a fix or default-off switch merged to the fork's `main` after its paired verification passed (`model-evolution` step 5), and the round now runs it | **P — patch in place** | the round's base did not change, so its knowledge base keeps its profile and directory and records the patch; only citations into changed lines need rewriting (PI, 2026-10-15). Adapter models only: `kb_patch` refuses a FATES profile, so a FATES change that lands is still C |
| **A new base binary** — a new round builds on a commit no registered profile covers, the diff from the old base is bounded, and no api epoch is crossed | **C — targeted drift refresh** | regenerate only the pages the diff invalidates, copy the rest forward into a NEW pinned directory, and register a new milestone (PI, 2026-08-14) |
| Source-grounded wiki exists, commit bumped **across** api epochs (e.g. api-31-0 → api-43-1) | **B — audit then rewrite** | catch semantic drift (inverted units, fabricated defaults) before re-canonizing |

**A vs B litmus:** if the existing wiki makes *semantic/behavioral* claims that can be
silently wrong (GDD thresholds, MPa↔mm unit inversions, formula direction), audit first
(B). If errors are merely *structural* (wrong filenames, off-by-N line numbers, nonexistent
dirs), greenfield (A) catches them without a separate audit pass.

### When the working model moves: Workflow P or C

**The wiki tracks the WORKING MODEL, not upstream releases.** Waiting for an api-epoch bump is the
wrong cadence: FATES milestones are rare and expensive, so a milestone-gated wiki stays stale for
months while the tree `A2MC_MODEL_PATH` resolves to has moved underneath it — and that tree is what
the agent reasons about. Fire on the *merge*, not the release: once an experiment branch has passed
its paired verification (`model-evolution` step 5) and merged to the fork's `main`, the change is
permanent in the model being run, and the wiki is now wrong about it. Before that merge the branch may
still be abandoned or reworked, which is why an in-flight branch is a **skip**.

**P or C is a question about the round's BASE binary, not about the size of the diff.** A registered milestone is the knowledge base for one calibration round's base binary. A change the round adopts on top of that base is a patch of its knowledge base (P); a new round built on a new base is a new milestone (C, or B across an api epoch). FATES has no P, because its knowledge base spans two checkouts and is versioned by api epoch, so a change landing in the FATES tree is still C. Never type a profile name: `python tools/kb_profile.py --model <m> --commit <sha>` names the profile covering a commit, and when none does, names the nearest one and how many commits AHEAD the commit is.

### Workflow P — patch in place (a fix on top of a round's base binary)

The profile keeps its name, its directory and its base commit, and gains a `patches` entry naming the commit it now describes, so `tools/kb_profile.py` resolves the base and every patched commit to the same profile. The directory name stays true because it names the round's base, which did not change; what the pages now describe is recorded in each page's `**Source pin:**` line and in the Patches table of the wiki's `index.md`, both written by `apply`, which also appends the patch to the milestone in `rag/milestones.json`.

```bash
$PY tools/kb_patch.py plan  --profile <p> --to <commit> --report <file>                         # changes nothing
$PY tools/kb_patch.py apply --profile <p> --to <commit> --summary "<one line>" --report <file>
```

`plan` classifies every `File:NNN` citation in the profile's wiki and curated seed against `git diff -M` from the knowledge base's commit to the new one: **untouched**, **shift** (the cited lines moved unchanged, and `apply` re-anchors them), **content** (the cited lines themselves changed) and **deleted**. Only shifts are rewritten. After `apply`, in order:

1. **Rewrite every content-flagged claim by hand** against the new source; the report lists them and `apply` leaves them as written. Check the bare `:NNN` citations the report says moved on position alone or could not attribute.
2. **Document each new source file** the report lists; a patch adds no page for it.
3. **Regenerate generated pages** with the command in their `**Generated by:**` line; `kb_patch` never edits them.
4. **Rebuild the SAME profile** (`rebuild-rag`) and run `validate-rag-chain`.

`kb_patch` refuses a FATES profile (its knowledge base spans the ELM and FATES checkouts and is versioned by api epoch: use the version-association tiers), a legacy profile, a commit that does not descend from the knowledge base's current commit, and a no-op. Full mechanics: the `tools/kb_patch.py` docstring.

### Workflow C — targeted drift refresh (a new base binary)

A full regeneration costs 100K–400K tokens *per subagent*. When the base moves but the diff
is bounded, most pages are still correct — regenerate only the ones the diff actually invalidates.

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

For an adapter model whose new base descends from the old profile's commit, `tools/kb_patch.py plan --profile <old> --to <new>` prints this classification for every citation and changes nothing; for FATES it is done by hand as above.

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
which is the one thing the commit-pinned convention exists to prevent for a new base (Workflow P edits in place because its base did not change, and records the patch). Give `index.md` the "What
changed" section Step 5 already requires for a bump, and say explicitly which pages were regenerated
and which were carried over — a reader must be able to tell how much of the wiki was actually
re-verified against the new source. Then run **`validate-rag-chain`** as usual: copied-forward pages
have *not* been re-checked against the new tree, so the citation validator is what catches a page
whose lines shifted further than the hunk analysis predicted. Register the new base as its own milestone in `rag/milestones.json` and build it (`rebuild-rag`); mark the old one `legacy: true`, which keeps it resolvable for the rounds that ran on it.

## Step 2 — stage inputs (read-only)

1. Clone or symlink the source checkout; **`git checkout` the exact commit** you're pinning.
2. Stage the parameter file (CDL/JSON/YAML) if the model has one, and the output registry from the model's own extractor (table below).
3. Decide topics: **5–10, aligned to source subdirectories**, not editorial taxonomy — so
   "where is X implemented?" maps mechanically to a wiki file. A cross-cutting module goes
   in the topic where it conceptually lives (e.g. FATES `EDMainMod.F90` → core dynamics, not
   biogeochem). Promote a calibration-critical doc to its own topic (FATES
   `advanced/cnp_calibration_guide.md` is its own topic for this reason). **Size by source
   LINE COUNT, not file count** — see "Cost & footguns" below before finalizing the split.

**The per-model tools this skill calls — one per model, not interchangeable** ([[feedback_per_model_scripts_not_generic]]):

| model | output registry (Step 2) | wiki ↔ source validator (Step 6) | generated reference pages |
|---|---|---|---|
| ELM / FATES | `scripts/extract_elm_outputs.py` for ELM; the FATES parameter and output CDLs are hand-managed (`rebuild-rag` Step 2b) | `tools/codebase_wiki_validator.py` | none |
| EcoSIM | `scripts/extract_ecosim_outputs.py` | `tools/validate_wiki_vs_source.py --model ecosim` | `tools/ecosim_param_source_map.py`; each page's `**Generated by:**` line has the exact command |
| PFLOTRAN | `scripts/extract_pflotran_outputs.py` (from the mass-balance tape) | `tools/validate_wiki_vs_source.py --model pflotran` | none |
| ATS | none on this line | `tools/validate_wiki_vs_source.py --model ats`, then `tools/validate_ats_wiki.py` for the Amanzi boundary and the deck's factory keys | none |

The FATES row is this line's copy of tools the CIME line (`A2MC-elm`) develops. Every knowledge-base BUILD step's tool for every model, in one table: [[reference_per_model_kb_build_tools]].

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

A new base creates a parallel `-<newhash>/` folder (traceability + rollback; FATES's loader is pointed at it by the `rebuild-rag` Recipe-1 symlink, an adapter milestone names it as `model_wiki_subdir`). A patch (Workflow P) keeps the folder. Write a top-level
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
- Then run the **`validate-rag-chain`** skill (Step 1, wiki↔source, with the model's validator from Step 2's table) — it automates the
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
- This is **step 1** of the adapter-kit pipeline → then `build-rag-from-scratch` for a new model, or `rebuild-rag` for a registered profile → `inject-knowledge`/curated YAML → `validate-rag-chain`.
- Branch note: codebase-wiki work is forward-dev — its natural home is `main`/adapter-kit.
  The api-31-0 wikis (`fates-codebase-wiki-e85d997`, `elm-codebase-wiki-60d9aad`) on
  a version-pinned manuscript branch are the reproducibility anchor; regenerate them only
  with explicit reason.

