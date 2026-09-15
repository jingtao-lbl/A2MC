---
name: cherrypick-from-main
visibility: public
category: meta
description: Bring `main`'s GENERIC improvements into `adapter-kit` by an audited, SELECTIVE cherry-pick (the current practice since 2026-07-15; a full merge is now the rare fallback). Use when the user says "merge main", "cherry-pick from main", "pull main's updates into adapter-kit", "update the branch from main", "sync from main", or before starting adapter-kit work after main has advanced. Codifies the audit-and-categorize pass (generic vs site-specific), the hard invariant (adapter-kit never rewrites FATES-shared files), the conflict-prone file list, and the verification gate. This direction is a SELECTIVE cherry-pick; the reverse direction exists too and is main's job — it RE-AUTHORS generic work from adapter-kit via its own adopt-from-adapter-kit skill, so adapter-kit never pushes but content does reach main. ALSO covers the other inbound direction (Step 7) — landing a FEATURE branch (`A2MC-adapter-kit-ATS`/`-PFLOTRAN`/`-surrogate`) into `adapter-kit`, where the default is INVERTED (full merge, not cherry-pick) — so it fires on "merge the ATS/PFLOTRAN/surrogate branch", "land the feature branch", "bring the branch back into adapter-kit" too.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [any]
  summary: "Inbound transfer into adapter-kit: from main by audited SELECTIVE cherry-pick (full merge rare), from a FEATURE branch by full merge unless it is contaminated (Step 7). No-FATES-rewrite invariant, keep-both resolution, verify gate."
---

# Bring work INTO `adapter-kit` (`main` by selective cherry-pick; feature branches by merge)

`adapter-kit` is a superset of main's **GENERIC CAPABILITY** — not a literal superset of main's
commits. It only ever **adds** (model adapters + generic tooling as NEW files), **never rewrites
FATES-shared files**, and **never *pushes* to `main`** — though `main` does take generic content from here, by re-authoring it (canonical: `docs/38` §3, `docs/40` §5,
memory `project_adapter_kit_branch_strategy`).

> **The transfer is a SELECTIVE CHERRY-PICK, not a merge.** `main` is the ELM / ELM-FATES line and
> carries site-calibration work (Kougarok, api-43) that `adapter-kit` deliberately does NOT want:
> pulling it would fork the generic tooling around one site. **The last wholesale merge was
> `f5529f6`, 2026-07-15**; as of 2026-07-30 `main` was 44 commits ahead on work adapter-kit
> intentionally omits. Being "behind main" is therefore the NORMAL, correct state — do not treat
> the gap as a backlog to clear.

A full merge is now the **rare fallback** (Step 6), not the default. For the OTHER inbound direction — a **feature branch** landing into `adapter-kit` — the default is inverted: see **Step 7**.

## Step 0 — Preconditions

- Confirm branch: `git branch --show-current` → must be `adapter-kit`.
- Clean tree: `git status --short` → commit/stash first.
- Fetch: `git fetch origin main`.
- Preview the incoming set: `git log --oneline adapter-kit..origin/main` and
  `git diff --name-only $(git merge-base adapter-kit origin/main) origin/main`.

## Step 1 — The hard invariant (check BEFORE merging)

adapter-kit must not have modified any **FATES-shared code file**. Verify:
```bash
BASE=$(git merge-base adapter-kit origin/main)
git diff --name-only $BASE adapter-kit | grep -E \
  'tools/(fates_utils|evaluate_case|codebase_wiki_validator|yaml_wiki_validator|rag_diff|check_rag_queries|modify_fates)|rag/(loader|vector_store|knowledge_graph|hybrid_retriever|graph_builder)\.py|scripts/build_rag_index\.py|orchestrator\.py|reasoning/'
```
**REVISED 2026-08-02 (PI).** Output here is a *prompt to check*, not an automatic violation. The
rule is not "never touch these files" — it is **never FORK them, and never break FATES**:

| adapter-kit did… | verdict |
|---|---|
| **generalized** a model-relevant hardcoding, FATES still the default and still working | **fine — this is the kit's PURPOSE.** `main` may stay FATES-hardcoded; it *is* the ELM/FATES line. adapter-kit may not, because A2MC must do the same thing for every onboarded model. |
| changed FATES *behaviour*, or made FATES a special case of something worse | **STOP** — that is a fork of the core |
| added an adapter-only branch that leaves FATES untested | **STOP** — verify FATES through the new path first |

So for each file that prints: read the diff, and answer **"does FATES still work, and is this
generalization or divergence?"** Worked example — `tools/yaml_wiki_validator.py` instantiated
`FATESParameterParser`/`FATESOutputParser` directly, so onboard-model's V2 gate was unreachable for
every adapter. Dispatching through the adapter registry with `--model` defaulting to `fates` is a
generalization: FATES behaviour is unchanged and every other model gains the gate.

What still matters is the **merge cost**: a file both branches edit can conflict. Expect it, resolve
by keeping the generalization and folding in main's change, and never resolve by reverting to a
FATES-only form here.

## Step 2 — Know the 7 conflict-prone shared files

Only files **both** branches independently edit can conflict. For adapter-kit that's a known,
small set (everything else adapter-kit adds is EcoSIM-only and absent from main):

| File | Why both edit it | Resolution |
|---|---|---|
| `rag/milestones.json` | both add milestone entries / `expected_counts` | **keep BOTH** — main's FATES entries + adapter-kit's `ecosim-*` entry. Never drop a FATES milestone. |
| `rag/golden_queries.yaml` | both add per-profile query blocks | **keep BOTH** blocks. |
| `.claude_memory/MEMORY.md` | both append index lines | **keep BOTH** sets of lines. |
| `TODO.md` | both maintain the checklist | **keep BOTH**; reconcile any duplicated item by hand. |
| `.claude/skills/README.md` | both add/edit skill-table rows | **keep BOTH** rows; if the same skill row differs, take the newer wording. |
| `docs/a2mc_reference/skills_catalog.md` | same, catalog form | **keep BOTH** entries. |
| `AGENTS.md` | skills "At a glance" table + operating rules | **keep BOTH** additions; preserve main's rule edits. |

Plus occasionally a **doc adapter-kit rewrote** that main also touched (`docs/17`, `docs/19`,
`docs/38`): keep adapter-kit's rewritten version and hand-fold any substantive main change.

The rule for every one of these is the same: **the merge should ADD, never DELETE** — a
resolution that removes a main-origin FATES entry is wrong.

## Step 3 — Audit and categorize (the core of this skill)

Never cherry-pick blind. Categorize every incoming commit first; **the file paths are the signal.**

```bash
git log --oneline adapter-kit..origin/main
git show --stat <sha>          # for each, to see the touched paths
```

| Category | Signal (paths touched) | Action |
|---|---|---|
| **GENERIC** | `tools/`, `scripts/`, `rag/`, `.claude/skills/`, `.claude_memory/`, `phases/`, `models/` | **cherry-pick** |
| **SITE-SPECIFIC** | `use_cases/{Model}_{Case}/` ONLY (e.g. Kougarok calibration rounds, param lists, phase logs) | **skip** — pulling it forks the generic tooling around one site |
| **ALREADY PRESENT** | message says "port/cherry-pick adapter-kit … to main" | **skip** |
| **MIXED** | generic + site-specific in one commit | cherry-pick, then `git checkout HEAD~1 -- use_cases/` to drop the site part, or hand-apply the generic hunk |

Record the categorization in a dev log so the pass is auditable and repeatable. Worked example with
the full table format: `memory/dev_logs_adapterkit/20260727b_Audit_CherryPick_Main_Generic_Capabilities.md`.

**Also diff the trees, not just the commits.** A commit-only audit misses deltas that arrived
bundled inside a port commit (that is how a main-only memory was nearly missed on 2026-07-27):
```bash
git diff --name-status adapter-kit origin/main | grep -vE '^.\s+use_cases/'
```

## Step 4 — Batch cherry-pick

```bash
git cherry-pick <shaA> <shaB> <shaC>        # the generic deltas, in main's chronological order
git cherry-pick <shaA>^..<shaB>             # a contiguous range
```
Resolve any conflict per the Step-2 table (keep BOTH). If a commit turns out to be mixed, prefer
`git cherry-pick -n <sha>`, unstage the site-specific paths, then commit.

If a conflict appears in a **FATES-shared code file**, do NOT resolve it casually — that is the
Step-1 invariant violation; `git cherry-pick --abort` and investigate why adapter-kit touched it.

**Carried-over citations.** A cherry-picked skill or memory may cite things that exist only on the source
branch. After the pick, check that every `[[wiki-link]]`, memory name, and doc path it references resolves
HERE — port, retarget to the local equivalent, or demote to prose. `memory-checkup` §"Porting a memory
across branches" has the rule; `offline-testing-workflow`'s Auto-memories block was a demo-branch carry-over
that cited three memories which never existed on `adapter-kit` (found 2026-07-31).

## Step 5 — Verify (post-transfer gate)

```bash
# EVERY onboarded adapter still intact — not just EcoSIM. `models/` has ecosim,
# pflotran and ats as of 2026-08-01; check each one you have.
for m in ecosim pflotran ats; do
  a2mc_env/bin/python tools/adapter_conformance_validator.py --model $m
done
a2mc_env/bin/python tools/validate_adapter_parity.py    # no NEW undeclared spec gaps
a2mc_env/bin/python -m pytest tests/test_ecosim_e2e.py -q                    # 4/4
a2mc_env/bin/python tools/check_ecosim_rag_queries.py                        # guard OK
a2mc_env/bin/python tools/check_skill_registry.py                            # registry parity
# FATES indices/milestones untouched by the merge
git diff --name-only HEAD@{1} HEAD | grep -E 'chroma_db/(api-43-1|api-31-0)' && echo "WARN: FATES index changed" || echo "FATES indices clean"
```
Confirm EcoSIM files survived (the merge should never delete `models/ecosim/`, the ecosim RAG, or
the new validators — they're adapter-kit-only, so main can't remove them; a diff showing them as
deleted means a bad resolution).

## Step 6 — When a FULL MERGE is still justified (rare)

Only when **every** incoming commit is generic — no `use_cases/{Model}_{Case}/` work at all in the range.
That was true before 2026-07-15 and has not been true since. Check first:

```bash
git log --name-only --pretty=format: adapter-kit..origin/main | grep -c '^use_cases/'
```
Non-zero ⇒ do NOT merge; cherry-pick per Steps 3-4. Zero ⇒ `git merge origin/main --no-edit` is safe.

**Never** use either mechanism to move an adapter-kit change TO `main` — that direction is
forbidden — adapter-kit never *pushes*. But the CONTENT does reach `main`: it re-authors generic work from here with its own **adopt-from-adapter-kit** (main's skill) skill (11 times to 2026-08-01). A generic improvement that belongs on main
must be authored/re-applied there directly.

## Step 7 — The OTHER inbound direction: a feature branch → `adapter-kit`

Feature branches (`A2MC-adapter-kit-ATS`, `-PFLOTRAN`, `-surrogate`) also flow **into**
`adapter-kit`. The Step 3-4 audit method transfers, but **the default is inverted**, so do not
apply this skill's headline rule to them:

| | `main` → `adapter-kit` (Steps 0-6) | feature branch → `adapter-kit` (this step) |
|---|---|---|
| Relationship | **two-way, both selective**: this skill takes from `main`; `main` re-authors from here via its own **adopt-from-adapter-kit** (main's skill) skill. adapter-kit never *pushes* — `main` pulls | the branch **lands back** when its work is ready |
| Default action | **selective cherry-pick**; full merge gated by Step 6 | **full merge** — that is what landing means |
| Go selective when | always | the branch is **contaminated** or says not to merge it |
| Version number | `main` owns it | the branch must **NOT** bump; bump here, at merge time |

**Read the branch's own handoff before deciding.** It may forbid the merge, and if it does, that is
authoritative — on 2026-08-01 the ATS branch's handoff said *"Do not merge this branch into
`adapter-kit`"*, because its RAG had been built from 9 output nodes when the real surface was ~39,
and two `ModelSpec`-keyed safety gates were silently dead for it. Merging would have propagated
known-wrong knowledge into the shared branch.

**When a branch is contaminated, split it by LAYER, not by commit.** Cherry-picking commits drags
the contaminated files along, because the two are interleaved. Take the kit-level generic tooling
(`tools/`, `scripts/`, `.claude/skills/`, `.claude_memory/`, dev logs) by path:

```bash
git checkout <branch> -- tools/<new_validator>.py .claude/skills/<name>/SKILL.md ...
```

and leave the model's own layer (models/<name>/, use_cases/<CASE>/, rag/*<profile>*, memory/<name>/) on the branch until its repair lands.

**Landing two branches in one pass — order by evidence, not size.** Merge the sound one **first**,
so the selective pass onto it resolves each file *knowing* what already landed, with cherry-pick
control rather than merge control. Compute the collision set up front:

```bash
comm -12 <(git diff --name-only adapter-kit...origin/<branchA> | sort) \
         <(git diff --name-only adapter-kit...origin/<branchB> | sort)
```

On 2026-08-01 that set was 5 files, and only one was a real contest: **both branches had
independently fixed the same defect in `tools/validate_model_targets.py`**, differently. Compare the
implementations and keep one whole; do not merge two fixes for one bug. (The better one errored
where the other silently fell through, and the loser's one unique change turned out to be inert.)

**Two traps specific to this direction:**

- **A feature branch that bumped versions.** The charter forbids it, but ATS bumped nine times and
  its logs cite those numbers. **Freeze `adapter-kit`'s version until every branch has landed**, then
  bump once — and if a branch has already renumbered into a range, jump over it rather than force a
  second renumber across its logs.
- **Carried-over citations** point at branch-only paths. Step 4's rule applies here with more force,
  because you are *deliberately* leaving files behind: the citation and registry contracts caught
  three on 2026-08-01 (models/ats/curated_seed.yaml, scripts/build_ats_rag.py,
  tests/test_ats_e2e.py — deliberately un-backticked here, since they are examples of
  branch-only paths, not citations this repo can resolve). Reword them as branch-qualified prose.

Worked example, both mechanisms in one session:
`memory/dev_logs_adapterkit/20260801b_Landing_Two_Adapter_Branches_PFLOTRAN_Whole_ATS_In_Half.md`.

## Cross-references

- `docs/38` §3 (branch discipline) + §8A — the strategy this enforces.
- `docs/40` §5 — the full transfer chain and each hop's mechanism.
- `memory/dev_logs_adapterkit/20260727b` — the worked audit + categorization this skill generalizes.
- Memory `project_adapter_kit_branch_strategy` — the decision record.
- `CLAUDE.md` Rule 11 (verify branch before commit/push) — this skill's Step 0.

