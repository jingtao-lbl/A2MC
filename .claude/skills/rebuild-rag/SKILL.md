---
name: rebuild-rag
visibility: public
category: kb-build
description: Rebuild or repair an A2MC RAG/GraphRAG index (ChromaDB vector store + NetworkX knowledge graph) that the ReasoningModule queries before every Claude API call — for ANY onboarded model, each of which has its OWN build script (FATES `build_rag_index.py`, EcoSIM `build_ecosim_rag.py`, PFLOTRAN `build_pflotran_rag.py`) with different flags. Use when the user asks to "rebuild the RAG", "reindex", "rebuild the EcoSIM/PFLOTRAN index", "bump the wiki to a new commit", "the RAG/index stopped working / returns nothing / returns stale content", "I edited the curated YAML — refresh the graph", "add a model to the RAG", or after any edit to a wiki / CDL / curated_relationships.yaml. Codifies per-model routing, the build pipeline, how to actually COMMIT the result (chroma.sqlite3 carries skip-worktree, so `git add` stages nothing and a rebuild is silently lost), and the footguns (loader pattern-probe symlink trap, --rebuild vs --graph-only, interpreter per machine, dropped curated edges, PFT-count env var).
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [rag]
  summary: "Rebuild/refresh the RAG index; model-agnostic."
---

# Rebuild the RAG/GraphRAG Index

The full reconstruction guide is **`docs/a2mc_reference/rag_build_roadmap.md`** — read it for
the architecture, file inventory, and Recipe 1/2 detail. This skill is the operational
runbook: pick the right rebuild mode, avoid the footguns, verify the result.

> **Interpreter, by machine.** Call it `$PY` below.
> - **Mac:** Python **3.10** from python.org —
>   `/Library/Frameworks/Python.framework/Versions/3.10/bin/python3`. Homebrew 3.12 fails on PEP-668.
> - **Perlmutter:** `~/a2mc_env/bin/python` (3.11) — verified to import `chromadb` +
>   `sentence_transformers`. A bare system `python3` fails ([[reference_perlmutter_a2mc_env_python]]).

## Step 0 — WHICH MODEL? There is one build script per model, and they are NOT interchangeable

**Do this before Step 1.** A2MC's *workflow* is generic; anything that reads a **model's own
artifacts** is a parallel per-model script ([[feedback_per_model_scripts_not_generic]]). Running
FATES's builder for a PFLOTRAN profile does not fail usefully — it writes into the wrong collection.

| Model | Script | Profile | Collection | Flags it accepts |
|---|---|---|---|---|
| **ELM / FATES** | `scripts/build_rag_index.py` | `api-43-1`, `api-31-0` | `fates_knowledge` | `--rebuild` `--graph-only` `--test` `--profile` `--allow-generic-cdl` |
| **EcoSIM** | `scripts/build_ecosim_rag.py` | `ecosim-2dea74d9` | `ecosim_knowledge` | `--rebuild` `--graph-only` `--no-write-counts` `--allow-shrink` |
| **PFLOTRAN** | `scripts/build_pflotran_rag.py` | `pflotran-157a26f7` | `pflotran_knowledge` | `--rebuild` `--no-write-counts` |

**The flag sets genuinely differ — do not copy a command across rows.** PFLOTRAN has **no
`--graph-only`** and **no `--allow-shrink`**; EcoSIM has **no `--test`**; only FATES takes
`--profile` (it is the only model with more than one).

Per-model behaviour worth knowing before you run:

- **PFLOTRAN refuses to write an empty graph** rather than emitting a profile that *looks* built
  (`build_pflotran_rag.py:25-28`). It also prefers the live mass-balance tape and falls back to the
  committed output registry `docs/pflotran-knowledge-base/pflotran_output_info_157a26f7.json`,
  saying **NEITHER** rather than silently building with zero output nodes (`20260806b`).
- **EcoSIM has a count-regression guard**: a >2 % drop in docs/nodes/edges vs `expected_counts` in
  `rag/milestones.json` fails the build. Bypass only with `--allow-shrink`, deliberately.
- **Both adapters write `expected_counts` back** into `rag/milestones.json` on success, which *arms*
  that guard for next time — so a rebuild normally dirties `milestones.json` too. Suppress with
  `--no-write-counts`.

> ### ⚠️ THE REBUILD WILL SILENTLY NOT COMMIT — read Step 4 BEFORE you build
> `rag/chroma_db/<profile>/chroma.sqlite3` carries `--skip-worktree` in every clone, so `git add`
> and even `git add -A` stage **nothing** and print no error. This is not hypothetical: it is
> exactly how the 2026-08-01 PFLOTRAN rebuild was lost (`20260806b` §Problem 3).

## Step 1 — classify the task (decision tree)

**Commands below are written for FATES.** For EcoSIM or PFLOTRAN, keep the *mode* column and
swap in that model's script and flags from Step 0 — e.g. PFLOTRAN's builder has no
`--graph-only`, so its "curated YAML only" row is a full `--rebuild`.

| What changed | Mode | Command (FATES; see Step 0 for the other models) |
|---|---|---|
| Edited `rag/data/curated_relationships.yaml` only | graph-only | `$PY scripts/build_rag_index.py --rebuild --graph-only --test` |
| Added/changed CDL definitions (`fates_params_info.cdl`, output CDL) | full rebuild | `$PY scripts/build_rag_index.py --rebuild --test` |
| Wiki content at a **new commit** (e.g. e85d997 → e027a40) | **Recipe 1** (below) | symlink first, then full rebuild |
| A **new model** entirely (EcoSim, ReSOM, …), or a full from-nothing build | use **`build-rag-from-scratch`** | that orchestrator owns wiki-gen + parser/loader registration; this skill is only the (re)index step it calls |
| Index "just stopped working" | diagnose first (Step 5) | usually Python version or empty `chroma_db/` |

**Never** rely on an incremental add for a content change: `add_documents()` dedupes by
`chunk_id` and silently SKIPS existing entries (`vector_store.py:110-127`). A wiki edit
that preserves chunk count but changes text is ignored unless you `--rebuild`.

## Step 2 — standard rebuild (current tree, no commit bump)

**For a registered milestone, this one line is enough and is guarded (v2.184):**

```bash
$PY scripts/build_rag_index.py --rebuild --test --profile <name>   # e.g. api-43-1
```

`--profile` resolves EVERY commit-pinned input (wiki subdirs, param file, FATES+ELM output CDLs)
from `rag/milestones.json` — the registered pinned filenames, else the milestone **anchor** commit.
You do NOT need `--fates-wiki-subdir` / `--param-cdl` / `--output-cdl` for a registered milestone
(the checkout HEAD is usually a *later* commit than the anchor, so deriving filenames from HEAD used
to silently fall through to the generic CDLs and shrink the index — the v2.183 near-miss).

Two guards now make that failure loud:
- **Input-contract guard** — if a registered milestone's resolved inputs don't match its registry
  entry, the build aborts (exit 2) before embedding. Override with `--allow-generic-cdl` only for a
  deliberate off-milestone build.
- **Count-regression guard** — a >2% drop in docs/nodes/edges vs the milestone's `expected_counts`
  fails the build (exit 3). Growth is fine; bump `expected_counts` when you legitimately add content.

Plain `--rebuild --test` (no `--profile`) still works for the active env profile.

Reads `docs/fates-knowledge-base/` + `docs/elm-knowledge-base/`, parses the two CDLs,
overlays `rag/data/curated_relationships.yaml`, writes `rag/chroma_db/<profile>/` +
`rag/graphs/<profile>.json`. Local, ~2 min, $0 (embeddings are local
sentence-transformers, not an API call).

## Step 2b — Recipe 1: bumping the wiki to a new commit-pinned tree

The **#1 footgun.** The loader probes wiki dir names and **stops at the first match**
(`rag/loader.py:366-371`), so a bare `--rebuild` keeps indexing the *legacy* tree even
though a commit-pinned `fates-codebase-wiki-e85d997/` exists. The build looks like it
succeeded but indexes the wrong content. Redirect with a symlink, archive the old
artifacts for rollback, then rebuild:

```bash
cd docs/fates-knowledge-base
git mv fates-codebase-wiki fates-codebase-wiki-legacy        # if a bare dir is in the way
ln -s fates-codebase-wiki-e85d997 fates-codebase-wiki        # point the probe at the new tree
cd -
mv rag/chroma_db rag/chroma_db.legacy_$(date +%Y%m%d)        # rollback safety
mv rag/fates_knowledge_graph.json rag/fates_knowledge_graph.json.legacy_$(date +%Y%m%d)
$PY scripts/build_rag_index.py --rebuild --test
```

Pair a wiki bump with a **CDL refresh** — the CDLs are hand-managed, not auto-regenerated
from source (`ncdump -h fates_params_default.nc > fates_params_info.cdl` against the FATES
build matching the wiki commit). See Recipe 1 in the roadmap for the full sequence.

## Step 3 — verify (do not trust a silent success)

```bash
$PY -c "
from rag import HybridRetriever
r = HybridRetriever(auto_build=False)
print(r.get_stats())
print(r.get_targeted_context(param_names=['fates_cnp_pid_kp'],
      output_names=['FATES_LEAFC'], mechanisms=['PID_Controller'], pft=10)[:1500])
"
```

- **Stats sanity:** current api-31-0 build is ~2,581 vector docs, ~1,295 graph nodes, ~2,197 edges (CLAUDE.md §RAG/GraphRAG).
  168 nodes means you ran a pre-Feb-2026 build — `--rebuild` again. 0 docs means the wiki
  path didn't match (the Step 2b footgun).
- **Content spot-check after a bump** (these are the claims that were wrong in the stale
  Feb-2026 index): phenology defaults `-68 / 638 / -0.01`, transpiration units in `mm`,
  and the phantom `fates_cnp_nfix` parameter **absent**. Open a matched `.md` and confirm
  it's the new commit's content, not legacy.
- **Coverage self-test (docs/33 §3c):** `$PY tools/check_rag_coverage.py --profile <profile>` —
  asserts every expected `kb_source` is present above a floor and canary wiki files appear.
  This catches the ELM-wiki-absent bug class (a whole KB silently dropped: `kb_source 'elm' = 0`).
  Update `rag/canary_queries.yaml` floors after a legitimate rebuild; the *presence* invariant should hold.
- **Golden-query content test (REQUIRED after any content change):**
  `$PY tools/check_rag_queries.py --profile <profile>`. Coverage is metadata-only — it does NOT
  catch a *wrong answer* (a bad SZPF ordering formula, a mislabeled PFT identity: dev_logs
  `20260710r/t`). This one runs the embedding model + graph and asserts real query results:
  `must_contain` / `must_not_contain` per query (e.g. the correct
  `iscpf = (pft-1)*nlevsclass+size_class`, the wrong `(size_class-1)*numpft` absent) plus a
  graph PFT-identity check (PFT10/11/12 = the api-43 arctic `fates_pftname`). Assertions live in
  `rag/golden_queries.yaml` — **add a query there for every new content invariant you fix** so a
  regression fails loudly next time. It self-verifies (a negative run does fail); exit 1 = wrong
  content, exit 0 = pass or gracefully-skipped (no embedding model).

## Step 3b — graph-only rebuild after a curated-YAML edit

```bash
$PY scripts/build_rag_index.py --rebuild --graph-only --test
```

Skips re-embedding (the vector index is unchanged) — seconds, not minutes. Watch the
build log for `skipped edge: endpoint not found`: a curated edge whose parameter/output
isn't in the CDL is **silently dropped** (`graph_builder.py:414`). Either add the endpoint
to the CDL or use the YAML curated-only fallback. (To inject a *new fact* across all three
memory channels before rebuilding, that's the `inject-knowledge` skill — this skill only
re-indexes what's already authored.)

## Step 4 — COMMIT the rebuild (the step that silently does nothing)

**A rebuild you cannot commit is a rebuild you did not do.** `chroma.sqlite3` is *tracked*, but
ChromaDB rewrites it on every **read**, so it would show as modified forever. Every clone therefore
sets `git update-index --skip-worktree` on it — which tells git to **stop looking at the file
entirely**.

Consequence, verified 2026-08-07 on a live 11 MB index that genuinely differed from HEAD:

```
git add <the sqlite>   -> stages NOTHING (message mentions "sparse-checkout", which is confusing:
                          skip-worktree is the same index bit, there is no sparse checkout here)
git add -A             -> stages 0 files
```

So `rebuild → git add -A → commit → push` yields a commit containing **everything except the new
index**, with no error. The graph (`rag/graphs/<profile>.json`) is plain JSON and commits normally,
so you get a **half-updated RAG layer that looks complete**. That is precisely the 2026-08-01
PFLOTRAN failure: the graph landed, the 1374-chunk vector index did not, and the committed index sat
at 1314 chunks with **zero curated content** until 2026-08-07.

**The sequence — un-skip FIRST, re-arm AFTER:**

```bash
F=rag/chroma_db/<profile>/chroma.sqlite3
git update-index --no-skip-worktree "$F"      # BEFORE the build, or at least before `git add`
$PY scripts/build_<model>_rag.py --rebuild    # (Step 0 picks the script)
git status --porcelain "$F"                   # MUST show " M" — if empty, the flag is still set
git add "$F" rag/graphs/<profile>.json rag/milestones.json
git commit
git update-index --skip-worktree "$F"         # re-arm, or read-churn dirties every later status
```

**Verify the commit actually contains it** — the whole failure mode is believing it did:

```bash
git show --stat HEAD | grep chroma.sqlite3    # must appear
$PY -c "
import chromadb; c=chromadb.PersistentClient(path='rag/chroma_db/<profile>')
col=c.get_collection('<collection>'); print('documents:', col.count())
print('curated chunks:', len(col.get(where={'source':{'\$contains':'curated'}}).get('ids',[])))"
```

A count that matches the *pre-rebuild* number means the old index is still what is committed.

**Audit any clone for the flag:** `git ls-files -v | grep '^S'` lists every skip-worktree file.

## Step 5 — when the index "just stopped working"

1. Wrong Python (must be 3.10 from python.org). 2. `rag/chroma_db/` exists and non-empty.
3. `rag/graphs/<profile>.json` exists. 4. `--test` the existing index. 5. Still
broken → `--rebuild`. Cross-CWD failures (Perlmutter) trace to path resolution
(`rag/hybrid_retriever.py` `_resolve_path`) and the NetworkX `edges="links"` JSON-key
compat fix (`20260204a`).

## Notes

- **Other knobs:** `A2MC_PFTS` sets the PFT list — always set it (the site config does)
  so the graph builds PFT-specific nodes for exactly your calibrated PFTs (e.g.
  `A2MC_PFTS=10,11,12` for api-43 Kougarok). If unset, `graph_builder.py`
  `_resolve_pft_list` falls back to a site-agnostic all-12-PFT default `[1..12]` **and
  prints a warning** — usable but not tailored to your site.
- **After a commit bump or curated edit, validate the chain** before trusting it — the
  `validate-rag-chain` skill (wiki↔source, YAML↔wiki, profile diff).
- **Where it lives in code:** the roadmap §8 has a grep cheat-sheet for every default path,
  the wiki subdir patterns, the chunk-ID/dedup logic, and the curated-YAML loader.
- Branch note: wiki *bumps* and new-model adds are forward-dev (mostly `main`/adapter-kit);
  on a version-pinned manuscript branch the common use is a `--graph-only` refresh after a
  curated-YAML injection. A pinned (e.g. api-31-0) index is the manuscript-reproducibility anchor
  — don't bump its wiki commit here without reason.

## Changelog

- 2026-08-07: **Per-model routing (new Step 0) + the commit step (new Step 4).** The skill was
  FATES-only in practice — every command was `build_rag_index.py`, and it mentioned PFLOTRAN zero
  times while `scripts/build_pflotran_rag.py` and `scripts/build_ecosim_rag.py` were referenced by no
  skill at all. Step 0 now routes to the right script and states that the FLAG SETS DIFFER (PFLOTRAN
  has no `--graph-only`/`--allow-shrink`, EcoSIM no `--test`, only FATES takes `--profile`), plus the
  per-model guards (PFLOTRAN refuses an empty graph; EcoSIM's count-regression guard; both write
  `expected_counts` back). Step 4 adds the step that had no home in any skill: **how to commit a
  rebuild**, since `chroma.sqlite3` carries `--skip-worktree` so `git add` and `git add -A` stage
  nothing and print no error — verified on an 11 MB live index, and the mechanism by which the
  2026-08-01 PFLOTRAN rebuild was lost (committed index stayed at 1314 chunks, zero curated, while
  the graph landed normally). Steps renumbered; the interpreter note is now per-machine (Perlmutter
  uses `~/a2mc_env/bin/python`, not the Mac's python.org 3.10). Description + all four registry rows
  updated in the same pass.

- 2026-06-17: Initial version — distilled from docs/a2mc_reference/rag_build_roadmap.md.
- 2026-06-17: Verify-pass fix — corrected stats sanity figure (~2,700 → ~2,581 docs / ~1,295 nodes) to match the api-31-0 index.
