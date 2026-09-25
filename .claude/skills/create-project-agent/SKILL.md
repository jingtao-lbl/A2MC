---
name: create-project-agent
visibility: public
category: meta
description: Stand up a PROJECT AGENT — an `A2MC-<Name>` repo whose framework half arrives by sync and is replaced on every run, and whose one top-level `<ProjectName>/` folder holds the project's goals, board, logs, scripts, skills, hooks and memory and must survive that sync. Use on "stand up a project agent", "create a project repo from A2MC", "turn this into a project folder", "organise X as a project in an A2MC repo", "set up a downstream project", "give this project its own agent", or when an existing standalone tree must be demoted to a project folder inside an A2MC repo. Serves a project that contains calibration as one part of it or a project not about calibration at all (such as analysis, model-evolution, examining mechanisms with onboarded models, etc.) as equal first-class cases. Declares ownership of every contested path BEFORE the first sync, because the sync is forward-only three ways over — an exclude does not retract, a .gitignore does not untrack, a merge cannot restore. NOT for wiring a fresh clone of an existing repo (use a2mc-init), NOT for adding a model (use onboard-model), NOT for creating a calibration case (use onboard-case). 
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [setup, meta]
  summary: "Repo topology and the project-folder contract; model-agnostic and calibration-optional."
---

<!-- ─── At a glance ─── -->
```text
  A2MC-<Name>/                          the repo. Framework half REPLACED on every sync.
  │
  │  ═══ FRAMEWORK HALF — the capability the project is wrapping A2MC FOR ═══
  │      41 include paths. Arrives by rsync, never edited here; a fix goes UPSTREAM.
  ├── docs/<model>-knowledge-base/      five of them: FATES, ELM, EcoSIM, PFLOTRAN, ATS
  ├── rag/                              RAG + GraphRAG retrieval over those, per milestone
  ├── memory/                           MemoryManager + the per-model knowledge stores
  ├── models/                           the adapter registry (EcoSIM, PFLOTRAN, ATS)
  ├── phases/ orchestrator.py reasoning/    the 7-phase loop and its AI interface
  ├── use_cases/TEMPLATE/ *_template/   case scaffolds only — no real case ever ships
  ├── tools/ scripts/ tests/ templates/ the harness: checkers, validators, generators
  ├── .claude/skills/ .claude/hooks/    the agent surface
  ├── .githooks/                        commit-time enforcement — the project CHAINS these
  ├── AGENTS.md a2mc_*config.sh docs/a2mc_reference/    contract, machine configs, reference
  │
  │  ═══ CONTESTED — both halves write these ═══
  ├── .claude/settings.json             SHARED WRITE. MERGED at sync, never copied.
  ├── CLAUDE.md  README.md              DESTINATION_OWNED banner. Hand-written; never arrives.
  │
  │  ═══ PROJECT HALF — everything the project authors ═══
  └── <ProjectName>/                    off INCLUDE + in DESTINATION_OWNED. Survives every sync.

  The framework half is not scenery. It is WHY a project wraps A2MC: the project needs
  some of that capability and should not re-implement it. It is SUBSET on two axes,
  and only the first is mechanical today.

    UNIVERSAL    every project gets it: tools/ scripts/ tests/ templates/ plot/
                 .claude/hooks/ .githooks/ AGENTS.md a2mc_*config.sh memory/ machinery
                 docs/a2mc_reference/ use_cases/README.md use_cases/TEMPLATE/

    (no RUNTIME axis -- the online half ships too.) phases/ is OFFLINE capability:
                 all eight offline phase skills call it. And orchestrator.py +
                 reasoning/ are 0.7 MB against rag/ at 91 MB, so dropping them saves
                 nothing and costs 8 DEAD-REFs from skills that cite them as the
                 online counterpart they are the offline analog of.

    by MODEL     docs/<model>-knowledge-base/   rag/ profiles   memory/<model>/
                 models/<model>/   use_cases/<Model>_template/   model-specific skills
                 A project investigating one model in EcoSIM has no use for PFLOTRAN's
                 or ATS's knowledge base, RAG index, adapter or run-workflow skill.

  Every model-scoped PATH is already named for its model, so that half derives itself.
  SKILLS do not, yet: `modes.scope` carries the model for 3 of them and not for the
  other 4 (`add-fates-parameter` and `offline-testing-workflow` say it only through
  `requires_fates`, the two `ecosim-*` adapter skills say `adapter`). Deriving a model
  subset from `scope:` today would ship EcoSIM skills to an ATS project and keep FATES
  skills for a project with no FATES. Normalising that declaration is a prerequisite,
  not a nicety -- it is the same shape as the `visibility:` derivation that already
  drives the private-skill exclusion, and it fails the same silent way when the field
  does not carry the fact.

  G1 topology ──▶ 1 name ──▶ [1b ADOPT] ──▶ G2 MANIFEST SIGNED ──▶ 2 bootstrap + seed
     ──▶ 3 repoint leg ──▶ 4 register in tests ──▶ 5 core nine + packs ──▶ 6 board
     ──▶ 7 contested surfaces ──▶ 8 gitignore ──▶ 9 front door ──▶ 10 log layers
     ──▶ 11 PROVE (M1..M12) ──▶ G5 FIRST REAL SYNC ──▶ 12 hand off + file the gaps

  G1 G2 G3 G4 G5 are HUMAN gates. M1..M12 are commands that must pass.
  Nothing is created before G1. No file is written before G2.
```

# create-project-agent — two halves, one namespace, ownership declared before anything is written

A **project** is the fifth unit of work. `a2mc-init` wires a CLONE, `onboard-model` adds a MODEL, `onboard-case` adds a CASE, `setup-discipline` collects what "finished" means for those three. A PROJECT is the only unit that owns a **repo topology**, and no skill owned it until this one.

The framework half arrives by sync and is **replaced on every run**. The project half is authored locally and must **survive** it. Every path both halves write is therefore a named conflict surface with exactly one of three resolutions — **MERGE**, **ACCEPT**, or **ABSENT-PLUS-GUARD**. All four failures this skill exists to prevent are the same omission: a contested path whose owner was never declared, discovered after a sync instead of before one.

So the first artifact is not a file tree. It is a **separation manifest**, derived by READING the leg's arrays at that moment rather than from memory, and the first gate is the PI signing it.

> ## Before Step 0 — prerequisites, each with a check you can run
>
> | prerequisite | check | if it fails |
> |---|---|---|
> | you are on `adapter-kit` in the dev clone | `git branch --show-current` prints `adapter-kit` | this skill authors a sync leg and edits `tests/`; it belongs on this branch only |
> | the clone is wired | `python3 tools/check_clone_setup.py` exits 0 | `a2mc-init` Step 1, then return here |
> | the design document is in hand | `sed -n '1,80p' docs/40_Downstream_Project_Repo_Pattern.md` | read it — this skill is the executable procedure over that design, and Step 12 files the four places it has drifted |
> | you are in an A2MC clone | `ls a2mc_config.sh tools/ .claude/skills/` resolves | this runs from A2MC, not from the project repo it creates | > | the getting-started tutorial is done | a wired clone, a built model, and a case with a completed round | the interview's two most consequential answers -- which models, and whether calibration is part of it -- are otherwise guessesachine; the leg never syncs it back, so `git ls-files` here will not find it** |
>
> **Anchor every command.** `A2MC_ROOT="${A2MC_ROOT:-$(git rev-parse --show-toplevel)}"` — an empty `$A2MC_ROOT` expands to the filesystem root, and a `rm -rf "$A2MC_ROOT/..."` written against it is unrecoverable.

---

## THE ASSEMBLY CONTRACT — fourteen rules, each ending in a command

These hold for every project folder inside a synced framework repo. They have nothing to do with headcount, with whether the project calibrates, or with what science it does.

**A1. ONE top-level folder, protected TWO ways.** Every project-authored file lives under a single `<ProjectName>/` that is **absent from the leg's INCLUDE list** (which is what actually protects it — measured 2026-09-02, when a team skill committed at the repo root's `.claude/skills/` was deleted by a real staged sync and named in the deletion report, while the identical skill inside the project folder was untouched) **and listed in `DESTINATION_OWNED`** so the guard hard-aborts if anyone re-adds it. Today the realised instance has only the first, while `.claude/skills/sync-downstream/SKILL.md` tells readers it has the second — that sentence is false, and Step 12 fixes it. The one-folder rule is also what makes the leg's FOREIGN UNTRACKED report correct by construction, since that report is a top-level heuristic and a project scattered across the root defeats it.

**A2. `.claude/settings.json` is MERGED — never copied, never excluded, never DESTINATION_OWNED.** It is the one file both halves must write, because Claude Code reads a repository's committed hook registrations from the repo root and nowhere else. Excluding it means a new framework hook never arrives; registering the project's hooks upstream ships a private folder name into the public repo. A leg that merges this file places the merge **after** the copy loop, so the copy cannot undo it, and **before** the leak scan, so the scan reads the merged result. **Its discriminator is the COMMAND PATH, not a name list**: `FRAMEWORK = "${CLAUDE_PROJECT_DIR}/.claude/hooks/"`, and an entry is kept as theirs iff that substring is **absent** from its command. Consequence, and it has been live in a real tree: a project hook registered with a command pointing into the framework's hooks directory is read as **ours**, deduped away or dropped when the framework retires that hook. Rewriting those command strings is a required step, not a cosmetic one.

**And the merge must read TWO sources, which is the half that was missing.** Reading the team's `main` alone is not enough the moment the leg writes to a pull-request branch: anything restored or added on that branch and not yet merged is invisible, so the merge preserves a source one commit behind and deletes the entry a second time — faithfully, which is worse than a bug because the output says it kept everything it found. Union `origin/main` with the destination's **last commit** (`HEAD:.claude/settings.json`), not its working tree: the copy loop has already overwritten the tree, but `rsync` cannot touch git's object store. Both sources through the same framework filter, so neither can resurrect a retired framework hook, and the report names which source each kept entry came from. This is A9 made concrete, and it was found only because the damage it protects against had already happened once.

**A3. `core.hooksPath` is single-valued, so CHAIN the two hook sets rather than choosing between them.** Git resolves hooks from one directory per clone, so pointing it at `<ProjectName>/.githooks` makes the root's ~25 numbered checks inert in that clone — silently, because a commit that runs fewer checks looks exactly like a commit that passes. **The answer is composition: the project's `pre-commit` ends by calling `"$ROOT/.githooks/pre-commit"` and accumulating its status**, so a commit gets both halves and neither directory has to win. Four lines, at the bottom of the project hook:

```bash
if [ -x "$ROOT/.githooks/pre-commit" ]; then
    "$ROOT/.githooks/pre-commit" || rc=1
fi
exit $rc
```

**This was left OPEN in the 2026-09-23 draft — "test it before asserting either way" — and was tested on 2026-09-24. It works**, and the reasoning that had made it look risky was right for the wrong reason: the framework's checks stay quiet on project work not by luck but because **every one is gated on a framework path** (`memory/dev_logs*`, `use_cases/`, `rag/`, `phases/`, `.claude/skills/`, `.claude_memory/`, `CLAUDE.md`), and none matches a project path. Measured: a project-only commit exits 0 with **zero bytes** on stdout and stderr.

**Assert the gating rather than trusting it.** It is a property of ~25 invocations that a later one can break without anyone intending to, so it needs a test that parses the hook and fails when a tool invocation sits outside a `git diff --cached` gate. Without that test, chaining is a bet on a habit.

**One framework check SHOULD stay ungated, and getting it for free is a reason to chain**: the oversized-blob guard. A host rejects a file over the size limit at **push**, when the commit already exists and the fix is a history rewrite — a hazard the project's artifacts share, and one the project would otherwise have to re-implement.

**Do NOT print `git config --unset core.hooksPath` as an escape for framework work.** The 2026-09-23 draft did, inherited from the pre-chaining world. Once chained it is actively wrong: unsetting loses the project's checks and changes nothing about the framework's, which run either way. **Leave it set, for framework work as much as project work** — and expect to find that sentence in three or four documents when you change this, because a hook contract is always written down more than once.

**What chaining does NOT remove:** the project's `commit-msg` still needs its own rules, because chaining `pre-commit` does not chain `commit-msg`. Chain that too, or accept duplicated rules and know that nothing detects them drifting apart. Both hook files must be **tracked** — `tools/check_clone_setup.py::_own_hooks_dir` accepts only a hooks path that is relative, inside the repo, an existing directory, and carrying a tracked `pre-commit` or `commit-msg`.

**A4. Every single-valued per-clone resource gets ONE declared owner, and the loser's check must return NA, not FAIL.** Three known: `core.hooksPath`, the harness memory symlink (one per clone root), and the author identity file. The hooks row is already fixed this way and is the template for the other two — **and note that A3's chain removes the contest for hooks specifically**: the project owns the path and the framework still runs, so there is no loser to return NA. The other two have no equivalent composition and remain genuine single-owner resources. The author row still fails a member who set only the project's identity file, and the memory row is latent, saved only because every leg excludes `.claude_memory/`, so a destination has no root bucket to contest.

**A5. A check that FAILS must name a fix that can actually make it pass IN THIS REPOSITORY.** Three recorded violations, one fixed and two open. For every framework row a project clone can fail, the manifest carries one line saying what makes it pass here.

**A6. The project owns its own nested `.gitignore` and never edits the root one.** The root file is generated wholesale on every run, so an entry added there is overwritten and an entry **missing** there has already deadlocked the leg against its own dirty guard. Reconcile both directions and prove with `git check-ignore -v`.

**A7. Skills NEST, hooks do NOT.** A subdirectory's `.claude/skills/` is discovered as **directory-scoped**, listed as `<ProjectName>:<name>`, with no registration (verified 2026-09-12), and needs only `name` and `description` frontmatter. `tools/check_skill_registry.py` scans only the repo root, so adding a project skill to the four framework registries fails as DRIFT — and the root `.claude/skills/` is an INCLUDE root, so a project skill placed there is deleted on the next sync. Hooks get no such treatment and must be registered in the root settings file. **A project skill duplicating a framework skill's name shadows it inside the folder** — rename it or reduce it to the delta, **but only when the framework copy actually lands in this destination**: a framework skill carrying `visibility: private` is stripped by every leg, nothing shadows, and the project copy is the only copy there will be.

**A8. Root `CLAUDE.md`, `README.md` and `AGENTS.md` are each classified explicitly at creation.** The first two are authored as the **project's banner** and added to `DESTINATION_OWNED` before the first sync, with the cost in writing — framework documentation stops arriving in them. The recorded reason is sharper than "wrong document": the shipped README calls the public A2MC "(this repo)" and says no case study ships, both FALSE anywhere else, and nothing upstream can fix a sentence that is true at home and false where it lands. **`AGENTS.md` goes through the same decision and is not exempt** — it opens by calling A2MC a calibration framework and routes every session to a router with no project awareness, which is the README failure repeated on the one agent-facing document still shipping. Because `DESTINATION_OWNED` is consulted only inside the INCLUDE loop and has **no existence check**, a new repo listing these ships with **none** of them unless they exist by Step 2. **Existing is not the same as written, and conflating the two is how all three ship generic.** Step 2 runs before the research-goal conversation, so anything authored there can only describe the scaffold; the scaffold therefore writes placeholders that are true of every project built this way and specific to none. They are **classified and created at Step 2, and WRITTEN at Step 5b**, once the plan exists to distil.

**A9. Forward-only is a law of the assembly, stated three ways.** An exclude hides a path so `--delete` never considers it and retracts nothing; dropping an INCLUDE path retracts nothing; a merge cannot restore what a merged commit deleted, and a merge sourced from the damaged branch faithfully preserves the damage. Therefore: protection is established BEFORE the first sync; **a recovery mechanism never takes its authority from a source the damage can reach**; the project folder keeps a committed inventory (`<ProjectName>/REGISTRATIONS.md`) of everything it registers so a restore is a diff rather than git archaeology; and every repair plan distinguishes the action that **stops** the damage from the action that **undoes** it, and schedules both.

**A10. Review asks whose CONTENT, not only whose PATH.** The deletion report lists only what `--delete` removes, so a content overwrite inside a path the leg legitimately ships matches neither the deletion report nor a grep of project-owned paths. The manifest's SHARED-WRITE column is the list the post-sync review walks, member by member.

**A11. Generic capability upstream, instantiation downstream — and the corollary runs both ways.** Model adapters, phases, tools, framework skills and RAG machinery never live in the project folder. Capability the **framework lacks** is raised with the PI rather than buried in a project folder.

**A12. Bind every derived fact to its source, and audit the scaffold for copies.** The realised instance has one violation not to repeat: a task-to-marker mapping exists as a hardcoded dict in one script AND as prose in a README, agreeing today with nothing comparing them, while the milestone-to-marker number IS on the board. Any such mapping goes on the board and both readers derive from it. The same rule kills docs/40 §8's version stamping, which is satisfied today by a `VERSION` file reading `2.127` while the source header says v2.450, checked by nothing.

**A13. Detection beats instruction, and that includes this skill's own artifacts.** Every runbook line this repo replaced with a script check held; every one left as prose was skipped. So: never hand-write a view of the board (generate it, banner it "GENERATED FILE. Do not edit." with its regenerating command in the first line, and re-render-and-compare inside `check`); make the project's setup checker **derive** its expectations rather than hardcode a name; and **make the leg itself re-derive and diff the separation manifest on every run**, because a manifest frozen by hand while its source array moves is exactly the confidently-wrong review answer this whole contract exists to prevent.

**A14. A filtered copy cannot satisfy the framework's own checkers, and chaining is what makes that visible.** The destination is built from a RELEASE, which carries less than the tree it was cut from — no development history, no case studies, no internal planning. Several framework checks are about exactly that content, so they report problems **no one in the destination can fix**. They sit harmless until A3's chain runs them, and then they block the team's commits for reasons that are not theirs.

Measured on the first chained run: **64 problems, 47 of them one checker demanding a section the sync itself strips** — two framework tools contradicting each other, latent for over a week because nothing had ever run a checker in a stripped tree.

So, at seeding time: **have the leg write a marker into the destination** identifying it as a downstream copy, and have the framework's checkers read it and report those classes as **advisory**. Three properties make the marker safe: it is **written by the leg, never copied**, so it cannot travel upstream; **its absence means STRICT**, so a partial clone or a worktree cannot soften itself by looking like a copy; and a marker found **beside** the development tree's own markers is treated as a mistake rather than a mode.

**Soften only what the tree cannot carry.** Everything about what it *does* carry must still block — registry parity, frontmatter validity, unbalanced private markers — or the check becomes an off switch and A13's detection-beats-instruction is lost. Verify by injecting a real violation into the filtered tree and confirming it still fails.

**And a new framework test or tool should declare whether it ships at all**, since `tools/` and `tests/` are whole INCLUDE paths and a file ships the moment it is committed. One header line (`visibility: public|private`) that the leg derives an exclusion from, mirroring whatever the framework already does for skills. Note the ceiling: a tool the shipped `pre-commit` invokes cannot be private unless that hook first learns to skip a missing tool.

---

## Decision tree

```text
  Is this a project (goals + state + its own agent bits), not a case or a model?
    no  ──▶ onboard-case (a calibration case) / onboard-model (a model) / a2mc-init (a clone)
    yes ──▶ G1: branch or repo?  docs/40 §2 triggers, PI decides, reason RECORDED
              │
              ├─ branch ──▶ the framework arrives by MERGE and merges are recoverable.
              │             A1, A2, A6, A9, A10 mostly evaporate; Steps 2-4, 8 and 11's
              │             sync proofs do not apply. STOP and re-scope with the PI —
              │             no branch-hosted project folder exists to copy.
              └─ repo ──▶ G1b: CREATE (greenfield) or ADOPT (an existing standalone tree)?
                            CREATE ──▶ Step 1 ──▶ Step 2 ...
                            ADOPT  ──▶ Step 1 ──▶ Step 1b ──▶ Step 2 ...   (rejoins at Step 3)

  Does the project calibrate?          -> decides whether use_cases/ is on INCLUDE at all
  Does the project RUN things?         -> decides the EXECUTION pack. INDEPENDENT of the above.
  Does it produce figures/manuscript?  -> decides the MANUSCRIPT pack
  Does it evolve model source?         -> decides the MODEL-EVOLUTION pack
  More than one person writes here?    -> decides the COORDINATION pack
  Packs COMPOSE. Zero is legal. Two is common. "Exactly one" is wrong.
```

## The gates

| gate | kind | what passes it |
|---|---|---|
| **G1** | HUMAN | Branch or repo, and which repo, decided by the PI against docs/40 §2. Nothing is created before this. |
| **G2** | HUMAN | The separation manifest is **signed**. No file is written before this. |
| **G3** | HUMAN | ADOPT only — how history travels. Irreversible-ish on a repo holding real work, no precedent exists. |
| **G4** | HUMAN | Packing — which packs, which INCLUDE delta, which SKILL-SURFACE delta, and whether the seven `visibility: private` framework skills ship to THIS destination. |
| **G5** | HUMAN | The first real sync. Every M below runs first. |
| **M1** | `--dry-run` read for BOTH the transfer list and the deletion report; `<ProjectName>/` appears in neither. |
| **M2** | Staged rehearsal into a throwaway destination that has an `origin` and the expected branch — a dry run cannot show the post-pass (private-block filter, changelog strip, path genericization, case-row pruning), and every filter defect this repo has found was found by staging. |
| **M3** | The subset is verified in BOTH directions: the models you asked for are present, the ones you did not are absent, and `grep -rl 'visibility: private' <dest>/.claude/skills/` returns nothing. |
| **M4** | `grep -rin '<donor-project-name>' <ProjectName>/scripts/ <ProjectName>/.claude/hooks/` returns nothing. |
| **M5** | The new leg appears in all five enumerating test files and `~/a2mc_env/bin/python -m pytest tests/ -k sync` reports a **nonzero ran-count** — "no tests ran" is not a pass. |
| **M6** | `git check-ignore -v` on every tracked binary in the project folder proves it is NOT ignored; and a second pass proves the must-ignore direction still holds for a generated artifact inside the folder. |
| **M7** | One **deliberate violation per project hook**, each BLOCKED after the path rewrite. Name what would make it fail before trusting that it passed. |
| **M8** | `python3 tools/check_clone_setup.py` and `python3 <ProjectName>/scripts/check_setup.py` both pass in the **same clone at the same time**. |
| **M9** | The project's setup checker **enumerates** `<ProjectName>/.claude/hooks/` and asserts each script is registered in the destination root settings file; delete one registration by hand and watch it name that script. |
| **M10** | `python3 <ProjectName>/scripts/state.py check` exits 0 — partitions, owners, dependencies, cycles, referenced paths, and every generated view re-rendering identically. |
| **M11** | `python3 tools/check_skill_registry.py` exits 0 after this skill is registered. |
| **M12** | **Cold clone.** Clone fresh, the project setup check exits 0, a session prints the board, a non-conforming commit is refused by the right layer, and `git status` is clean. |

---

## Step 0 — decide the topology, and record whose decision it was  **[G1]**

Walk `docs/40_Downstream_Project_Repo_Pattern.md` §2's triggers out loud with the PI. External write access is decisive on its own; its own release cadence and licence-encumbered data are not; and "the project involves a lot of files" is **explicitly not a trigger**.

**Say plainly when the triggers point the other way.** A single-person manuscript project with no external write access fails the decisive trigger and meets only the two non-decisive ones, so §2's own default is a **branch** — and the PI may nonetheless name an `A2MC-*` repo. Do not resolve that silently: write the PI's reason into the project's `CLAUDE.md` as one line, because nothing in the repo records it today. Flag, without fixing, that docs/40 §8 step 1 forbids the `A2MC-<Project>` name that both the realised instance and the PI's target shape use.

Then pick the MODE. **OUTPUT: four lines** — repo-or-branch, which repo, the reason, CREATE or ADOPT.

## Step 1 — name the folder and prove the name is safe

The project is **one** top-level directory. Convention: the folder carries the project's own name -- what the people in it call the project, not what the repository is called -- and need **not** derive from the repo name — nothing in the leg derives one from the other. Ask rather than derive.

```bash
A2MC_ROOT="${A2MC_ROOT:-$(git rev-parse --show-toplevel)}"
sed -n '/^UNIVERSAL=(/,/^)/p' "$A2MC_ROOT/scripts/wrap_for_project_agent.sh"   # what always travels
ls "$A2MC_ROOT"        # and what is at the top level, which is what a name can collide with
```

The name must not be, nor prefix, any include root: `.claude`, `.githooks`, `scripts`, `tools`, `tests`, `phases`, `rag`, `models`, `templates`, `reasoning`, `plot`, `memory`, `docs`, `use_cases`.

## Step 1b — ADOPT only: demote an existing repo root to a nested folder  **[G3]**

Run this **before** Step 2, because for an adopted tree the folder's contents and its git history decide how the destination comes into existence.

**G3 first.** Moving history under a `<ProjectName>/` prefix (filter-repo or subtree) yields a combined clone every framework pull also carries; starting fresh and freezing the old repo as an archive loses the provenance that is often the repo's stated purpose. There is **no precedent** — the realised instance was authored in place, never migrated. Present both costs and stop.

Then enumerate what collides, before moving anything:

```bash
SRC=~/<existing-tree>
ls -A "$SRC"                                  # every top-level entry
git -C "$SRC" ls-files | grep -E '\.(nc|h5|tar\.gz|csv\.gz|pt|joblib|npz)$'   # tracked binaries
python3 -c "import json;d=json.load(open('$SRC/PROJECT_STATE.json'));print(list(d.keys()));print(sorted({k for x in d.get('tasks',[]) for k in x}))"
grep -rn 'CLAUDE_PROJECT_DIR' "$SRC/.claude/settings.json" "$SRC/.claude/hooks/"
git -C "$SRC" config core.hooksPath ; ls -l "$SRC/.git/hooks/pre-commit" 2>/dev/null
```

Six mechanical consequences of demotion, **each of which fails silently if missed**:

1. The tree's top-level `.claude/settings.json` **stops being read**. Its registrations move to the destination repo root with `${CLAUDE_PROJECT_DIR}/<ProjectName>/...` commands — and per **A2**, a registration left naming the framework hooks path is classified as ours and dropped by the merge. A tree whose four hooks all use the framework-shaped path is four silent losses waiting.
2. Each hook's **own root resolution** must ALSO gain the project prefix. A hook resolving `CLAUDE_PROJECT_DIR or getcwd()` will look for `figures/` and `benchmarks/` at the repo root, find nothing, and **PASS**. M7 is the only thing that catches this.
3. Skills keep working unchanged as directory-scoped skills — but any whose name duplicates a framework skill now **shadows** it inside the folder, and a fork that was a superset when copied can be a hundred lines behind by now. Rename or reduce to the delta, subject to the **A7** exemption for framework skills the leg strips.
4. A `.git/hooks` symlink arrangement **stops running entirely** the moment `core.hooksPath` is set anywhere in the clone — a third variant of the hooks failure that fails **silent** rather than loud.
5. The tree's own `.gitignore` moves to `<ProjectName>/.gitignore` (**A6**).
6. A machine-local memory bucket (unvalidated, not under git, its size usually a skill's own estimate rather than a count) is migrated into `<ProjectName>/.claude_memory/` with frontmatter. **This is normally the single largest gain of the whole move.**

**Board reconciliation is part of ADOPT, not an afterthought.** An existing board will not match the scaffold: expect extra keys, a partition that is a label rather than a folder, and missing `owner`. Carry it over as-is and make Step 6's `check` conditional on the keys it actually has — do not rewrite someone's 49 tasks to fit a template.

## Step 2 — run `--init`, and read what it refuses  **[G2]**

One command builds the destination. Everything this step used to do by hand — bootstrap the repo,
hand-write the banners, register the project's hooks before the first copy, derive the manifest,
copy the framework half, write the downstream marker, scaffold the project folder, wire
`core.hooksPath` — is inside it, **in that order**, because the order is the protection.

```bash
scripts/wrap_for_project_agent.sh --init \
    --project <ProjectName> --dest ~/A2MC-<Name> --models <a,b or omitted> [--remote <url>]
```

Run it from your A2MC clone. If it refuses, it says what it found and what to do.

**`--models` is the decision that matters**, and omitting it is a real answer. It selects the
knowledge bases, RAG profiles, adapters, case templates and model-specific skills that travel, and
those paths are most of the tree — a project with no calibration takes none of them and gets the
harness alone. The skill subset is **derived** from each skill's `modes.scope` by
`tools/skill_models.py`, never from a hand-list, and the derivation **fails loudly** rather than
shipping an unfiltered set, because "every model's skills went to a project that asked for one"
looks exactly like success in the output.

**What `--init` writes before any framework path lands**, and why the order is not negotiable:

| | |
|---|---|
| root `CLAUDE.md`, `README.md`, **`AGENTS.md`** | the project's own. `AGENTS.md` is on no include list: A2MC's opens by calling itself a calibration framework, true there and false here. Listing it has the copy overwrite the project's — measured. |
| the destination's `.claude/settings.json` | carrying the project's hook registrations, **before** the framework's file could land and win |
| `<ProjectName>/SEPARATION_MANIFEST.yaml` | **derived** from the include list actually used, never hand-written, so it cannot freeze while its source moves (A13) |
| `.a2mc-downstream` | so the framework's own checkers read this tree as a filtered copy (A14) |

**G2: read the manifest and sign it before committing anything else.** It is generated, so signing
it is reading what the machine decided rather than restating what you intended.

## Step 3 — verify the subset, because absence is what a check cannot see  **[M3]**

A model you did not ask for leaves no trace, so "PFLOTRAN is absent" is true in a tree where
**nothing** landed. Check both directions or the check is vacuous — that exact false pass happened
on the first build of the reference project, where `.claude/skills/` had been omitted from the
include list and every model's skills were absent together.

```bash
D=~/A2MC-<Name>
# the models you asked for MUST be present
ls -d $D/docs/*-knowledge-base $D/models/*/ $D/use_cases/*_template $D/.claude/skills/*run-workflow
# the ones you did NOT ask for must be absent -- name them explicitly, do not eyeball the listing
```

If a model you did not ask for is present, or one you did is missing, stop and fix `--models`
rather than editing the destination: a later `--refresh` recomputes the subset from the manifest,
so a hand correction is undone on the next run.

## Step 4 — the project's own setup check decides  **[M5]**

```bash
cd ~/A2MC-<Name> && python3 <ProjectName>/scripts/check_setup.py
```

Every row must be ok before anything else. It is **derived**, not hardcoded: it enumerates the
hooks the project actually ships and asserts each is registered, so adding a second hook cannot
leave the checker silently satisfied by the first (M9).

The framework's own `tools/check_clone_setup.py` also lives here and is **advisory** in a project
repo — it is written for a standalone A2MC clone, and where the two disagree the project's wins.
State that in the project's `CLAUDE.md` rather than leaving a reader to discover it.

## Step 5 — adapt the scaffold; it is GENERATED, not copied  **[G4]**

`--init` wrote the project half from `scripts/_wrap_scaffold.sh`, so it is reproducible and carries
no other project's vocabulary. An earlier design scaffolded by **copying a live instance**, which
needs a donor the user does not have and drifts toward whatever that one project happened to grow.

What lands, and what you must now do to it:

| artifact | generated as | your job |
|---|---|---|
| `RESEARCH_PLAN.md` | four empty prompts | **fill it in first.** A board built before the plan holds tasks nobody can justify |
| `PROJECT_STATE.json` | schema + one task ("fill in the plan") | add the project's real tasks, people and key facts |
| `<Project>/CLAUDE.md` | the session contract | add what an agent must know here that is not generic |
| root `README.md`, `CLAUDE.md`, `AGENTS.md` | placeholders | **Step 5b** — they are the repository's face and nothing can detect that they are still generic |
| `TODO.md` | generated from the board | **never hand-edit**; regenerate with the project's own `todo.py` |
| `scripts/` | `state.py` `todo.py` `check_log.py` `check_setup.py` | extend, do not rewrite — the pre-commit hook calls them by name |
| `logs/README.md` | the log contract | adjust the header fields if the project needs more |
| `.claude/hooks/session-start.py` | prints the board | add what a session here must see first |
| `.githooks/pre-commit` | project checks, then **chains** the framework's | add project rules above the chain, never below it |

**Do not add a stream, a roster or a commit-debt rule because the reference project has them.**
Those answer *several people writing one board*. A solo project that inherits them gets ceremony
with no conflict to prevent, which is how a scaffold stops being used.

## Step 5b — write the three ROOT documents, from the plan  **[G4]**

**Do this after the research-goal conversation and after `RESEARCH_PLAN.md` is filled — not at Step 2.** A8 classifies `README.md`, `CLAUDE.md` and `AGENTS.md` as the project's own and they are created by `--init`, but what `--init` can write is a placeholder: at that point the project has not been described to you. These three are a **distillation of the plan**, and written before it they are invention.

**Nothing detects that they are still generic.** They parse, their links resolve, every checker passes, and `--refresh` never touches them. So the placeholder survives to the first real session and routes a reader by a description of the scaffold instead of the project. Measured on a project built to exercise this script: all three shipped untouched at 629, 922 and 422 bytes, against a real project's 66 KB, 22 KB and 4.4 KB. Nothing in the assembly complained, because there was nothing to complain with.

| file | who reads it, and how they arrive | what it must carry once it is the project's |
|---|---|---|
| `README.md` | a person, often from a link, with no context at all | what the project is in two sentences — the science, the programme or award if it has one, who leads it; **which repository this is and which it is not**, since a project repo and the framework's own public repo are easy to confuse; a *you want / read* routing table; what is the project's to edit; where data lives that is not in git |
| `CLAUDE.md` | an agent landing at the repository root | a **banner read before the rest of the file**: what the project is doing *right now*, as phases in order with the state of each and which one is current; then where work goes, and the branch and pull-request policy. Any framework reference sits **below** the banner and is labelled as reference, with the version it was frozen at |
| `AGENTS.md` | any harness-neutral agent | this project's operating contract — what to run at session start, what to read in what order, and the two or three rules that are not negotiable here |

**Write the banner against the wrong turn you can actually name.** A project whose calibration is a later phase will otherwise have agents arrive and try to run a round, so the phase table exists to make arriving at the wrong phase obvious. Say plainly what has **not** started, and why the order is what it is — an ordering nobody can justify gets re-litigated every session.

**Say in all three that they are the project's own**, because `--refresh` replaces the framework half around them and never these: what they claim is kept current by this project's own housekeeping or not at all.

```bash
# 1. the scaffold's own sentences must be GONE from all three
grep -n "A project repository built on the A2MC framework" README.md CLAUDE.md AGENTS.md \
  && echo "STILL THE SCAFFOLD -- do not hand off"
# 2. the project's SUBJECT, in the words RESEARCH_PLAN.md uses, must appear in every one
for f in README.md CLAUDE.md AGENTS.md; do printf '  %-12s %s\n' "$f" "$(grep -ci '<subject>' "$f")"; done
```

## Step 6 — the board, and its integrity gate  **[M10]**

**Ten keys both instances invented independently:** `schema`, `project`, `updated`, `updated_by`, `note`, `plan`, `key_facts`, `decisions_open`, `decisions_closed`, `tasks`. `key_facts` as a flat dict of short prose facts is a cheap, proven slot for the handful of things every session needs and no document owns.

**Task record:** `id`, `status`, `subject`, `detail`, `blockedBy[]`, `notes[]`, plus **optionally** a partition key and `owner`. The status enum is exactly `{pending, in_progress, completed, blocked, abandoned}` — **put a comment in the template saying `done` is the word people reach for and is NOT a status**, because the realised instance's own guidance said `done` until 2026-09-11 and would have failed anyone who copied it. **Namespace ids by collection** (T/D/M/C prefixes): the live board has `C1` as both a closed decision and a chore, harmless only because the two are read separately.

**`state.py check` is the project's integrity gate.** Validate at minimum: the status enum; owners and co-leads resolve; `blockedBy` resolves; no dependency cycles; every referenced doc or skill path exists; and **every generated view re-renders identically** to what is committed. Cross-checking the board against the **filesystem** is what catches a reorganisation.

**Every rule is conditional on the key it reads.** Partition-exists-as-a-folder runs only when the partition names folders; it returns NA for a label-only partition (P0..P7, PM is a real board in production). Owner-resolves runs only when tasks carry `owner`. A `check` that fails 49 of 49 tasks on the only non-calibration board in existence is a scaffold generalised one instance too far.

**Model recurring work as CHORES, not tasks** — `cadence_days` + `last_run` + a skill path. A task closes; a chore returns, so `completed` says nothing about it and only when it was last done carries information. Surface only the **due** ones at the top of the generated TODO. Seed every project with the housekeeping chore, since the record drift this whole structure creates is exactly what a periodic sweep exists to repair.

**Plain stdlib, Python 3.6 compatible** — a bare `python3` on Perlmutter is 3.6 and a utility people run casually must not need a module load.

**Deliverables are SEPARATE from the board, and a solo project needs them too.** Every deliverable gets a document whose definition-of-done is written **before** the work, with why it is the right test and what it deliberately does NOT demonstrate, dependencies by id, an Evidence section appended as evidence appears, and a dated status log — mirrored on the board with owner, status, doc path and `evidence[]`. Three operating rules: **argue the metric early** (a metric agreed after the results exist is not a metric), attach evidence as it appears, and **say when something is NOT met**. Do not gate this on headcount — the funded-project apparatus (markers, Gantt, sponsor artifacts) is COORDINATION, but "the one artifact that means this is finished" is not.

## Step 7 — wire the four contested surfaces, each with a proof  **[M8, M9]**

**(a) The root settings file.** Register the project's hooks in the **DESTINATION repository's** root `.claude/settings.json` — never in the framework clone's, which would ship a private project folder name into the public repo and is forward-only in the one direction that cannot be undone — with commands naming `${CLAUDE_PROJECT_DIR}/<ProjectName>/.claude/hooks/<name>.py`, which is precisely what makes the merge's discriminator classify them as theirs (A2). Distinguish, in writing, a **committed** registration (root settings, shared, travels, the merge surface) from a **local** one (`.claude/settings.local.json`, per-clone, untracked, repairs one person and reaches no teammate).

**(b) `core.hooksPath` — set it to the project's directory and CHAIN the framework's (A3).** Make the project's hooks directory **tracked**, end its `pre-commit` by calling `"$ROOT/.githooks/pre-commit"`, and chain `commit-msg` the same way or accept that its duplicated rules will drift with nothing detecting it. **Two proofs, both cheap:** stage a project-only change and run the project hook directly — it must exit 0 with no output; then empty one of the project's own rule lists and confirm a violation is still refused, which is what shows the chain is live rather than the local copy doing all the work. Do not write the `--unset` escape into any document (A3).

**(c) The harness memory bucket.** One per clone root. **Assert the framework's root `.claude_memory/` is absent from or excluded by the leg before wiring**, then wire with an idempotent `setup_memory.sh --wire/--unwire` that moves an existing bucket to `<bucket>.pre-symlink-bak` rather than deleting it. Say the cost out loud: everything the agent saves while working in this repo now lands in a committed, visible folder. Give the bucket its **own** 7-field frontmatter schema (`name` equal to the filename stem, `description`, `author`, `scope`, `type`, `source` — a memory with no source is an assertion — plus `shared: true` when several people write) and its **own** checker, because the framework's scans the repository root and speaks A2MC's vocabulary. Enforce name/stem equality, index parity in both directions, snake_case filenames, and a ban on personal host paths. Note that a wired bucket is **branch-scoped content**: `git checkout` silently changes what a running session can recall, so re-read the index after switching branches mid-session.

**(d) Identity.** **Two files with the same basename and different meanings** — the framework's root one (a display name) and `<ProjectName>/.me` (a roster id, gitignored). **Set BOTH**; they are not alternatives. Resolve, never default: env var, then the project file, then git config matched against the roster, then **EXIT 1 with instructions**. A default here is a wrong attribution that nobody notices, and a wrong author looks exactly like a right one. Keep this even for a solo project — the artifact outlives the single author. Ask the person rather than inferring from git history, the hostname, or the previous log's author.

**Pair every wiring script with `--unwire`, and say what you wired.**

## Step 8 — reconcile the two ignore files, and prove BOTH directions  **[M6]**

The leg **rewrites** the destination's root `.gitignore` wholesale on every run from a heredoc that looks generic and is not.

**Pass 1, must-ignore.** The generated block must be a **superset** of the source repo's per-clone artifacts. It omits the framework's own identity and greeting markers today, which is the same class of omission that once left a build directory untracked, the working tree permanently dirty, and the leg's own dirty guard refusing every subsequent sync.

**Pass 2, must-track.** Its `*.nc`, `*.h5`, `*.tar.gz` patterns are **unanchored** and match at any depth, including inside the project folder:

```bash
git -C ~/A2MC-<Name> ls-files | grep -E '\.(nc|h5|tar\.gz|csv\.gz|pt|joblib|npz)$'
git -C ~/A2MC-<Name> check-ignore -v <each-path>     # must report NO match
```

Either add per-path negations to the generated block following the leg's own recorded rules — a negation must **repeat the FILE pattern** (a directory negation alone leaves the file rule in force), `/**` is needed to re-include intermediate directories, and the last matching pattern wins so the block goes last — or write them into `<ProjectName>/.gitignore`. **Prove it with `git check-ignore -v`, never by reasoning**: the leg's own comments record two cases where a negation looked right and did nothing, and the failure is **silent by construction**, because gitignore governs untracked files and nothing errors. A wholesale `!<ProjectName>/**` negation works but shifts the **entire** ignore burden onto the nested file, so pass 2 must also prove a generated artifact inside the folder is still ignored — a cold clone cannot see this, because it has generated nothing yet.

Put the reason in the nested file's own header: *this file, not the repository root's; the root one is rewritten wholesale by the sync.*

## Step 9 — the project's front door, its light checkers, and BOTH hook kinds  **[M7]**

**Declare which check decides.** In a repo carrying a project folder, the **project's own setup check is authoritative** and the framework's session-start relay is **advisory**. State this in the project's `CLAUDE.md` and its onboarding document, because `tools/check_stage_ready.py` and `.claude/hooks/session-start.py` contain **zero** project awareness — verified by grep — and will still tell a correctly onboarded member their clone is not set up and point them at a fix that used to break the project's own configuration. Route first contact through the project's own `<ProjectName>:onboard` slash command, which reaches the harness by a path the framework's greeting hook does not handle. **Say in the same breath that a printed instruction is the weak half of the fix**; the detector is the strong one, and Step 12 files it.

**Project skills** live at `<ProjectName>/.claude/skills/<name>/SKILL.md`, need only `name` + `description`, are discovered as `<ProjectName>:<name>`, and must **never** enter the four framework registries (A7). Give the folder its own skills README stating the scoping rule and its own "what does not belong here".

**Its own light log checker.** Convention `YYYYMMDDx_Topic_In_Title_Case.md`, a short fixed header (Date, Author, Stream-or-Area, Status, Task), free prose below, author **not** in the filename, the letter scoped **per folder** so a collision is a real error, and the past-`z` rule `za, zb, ... zz, zza` (the naive `aa, ab` sorts before `b` and is wrong). The checker validates the filename and the header **only** and reads nothing below the rule. **Record the refusal to add a section contract as a DECISION with its reason** — these logs are for people, and a barrier to writing costs more than a format gains — so the next agent does not helpfully add one. The project ships its own checker because the framework's fails rather than skips an unrecognised stream; state that as a negative rule in three places.

**Both hook kinds.** A **SessionStart** hook that prints the board, what is ready, what you own and what to do first; and **PreToolUse** blockers for the disciplines that have actually been violated. A project with only blockers tells a fresh session nothing until it does something wrong; one with only reminders enforces nothing. **Every hook fails silent and exits 0 on every path**, and says so in its own docstring — a hook that errors at session start is worse than a hook that is absent, because the person it fails on is the person who has not yet learned what it does. **Never re-resolve a fact a script already owns**: call the identity resolver, import the shared counter. Two resolvers for one fact is one resolver too many.

**Enforce at both layers from one implementation.** The strictly better pattern, and the one to copy: the project's git `pre-commit` does not reimplement the agent-side hooks — it **feeds each one a synthetic payload** and treats a deny decision as a failure. One implementation, two trigger paths.

**The setup checker derives, never hardcodes (M9).** It enumerates `<ProjectName>/.claude/hooks/` and asserts each script is registered; the realised instance hardcoded one hook name and therefore said nothing at all when **both** registrations were deleted. Wire that same parity check into the project's pre-commit and its SessionStart hook so it runs continuously rather than once, and make `<ProjectName>/REGISTRATIONS.md` the file it reads — a committed inventory that nothing checks is a document, not a detector. **Onboarded is defined as that checker exiting 0**, every row required, each printing the exact fixing command, and **finishing it is the agent's job** — a half-set-up clone is work the agent can complete, and unfinished here is silent.

## Step 10 — "no work without a log", in layers  **[M12]**

Four independent layers, because the failure mode is drift rather than miscommunication, and one layer is one place to forget: `state.py set <id> completed` **refuses** unless some log header names the task, with a `--force` that writes CLOSED WITHOUT A LOG into the notes (possible, never silent); `state.py check` **errors** on a completed task no log names, so hand-editing the JSON does not get round it; the pre-commit **refuses** a commit staging work artifacts with no log beside them; and a commit-debt counter **warns** at 3 and **refuses** at 5, with the agent-side reminder importing the **same** counter as the git hook so the two cannot disagree. **Keep all four for a solo project.**

Alongside it, name the three things that are **not the agent's to close**: a decision with a named owner (*do not resolve it because the analysis pointed one way — that is the one place an agent working ahead does real damage*), a verification gate that an exit code does not pass, and a task whose work is done but whose checkable evidence does not exist.

## Step 11 — prove the assembly  **[M1-M12, then G5]**

Run M1 through M12 **in order**, all before anything irreversible. Then, and only then, the first real sync.

**Standing precondition on every sync, the first one included:** the destination's default branch already carries the project's current hook registrations, because the merge reads that branch as the authority and will otherwise faithfully preserve their absence. The measured margin on the near-miss was 43 minutes. Step 2b is what makes this true at creation; the Step 3 detector is what keeps it true afterwards.

**Two more runbook preconditions.** The working tree must be clean **repo-wide, including the project folder** — the dirty guard is tree-wide by design, `--allow-dirty` requires having looked, and *a dirty project folder blocks the framework sync by design rather than by accident*, which belongs in the project agent's definition of done. And **stage by explicit path, never `git add -A`**; read the deletion report **and** the foreign-untracked report before the commit.

## Step 12 — hand off, and file what this skill could not fix

**Route onward:** the `sync-downstream` skill for every sync after the first; `onboard-model` and `onboard-case` if the project needs calibration; `add-skill` for framework skills **only**.

**State in the project's own README that work here does not reach the framework automatically, and that this is routing, not a restriction** — build what the project needs here, and folding something upstream is a separate, deliberate coordination step in the development repo.

**Then file three framework changes this skill cannot make from inside a project folder, and bring them to the PI rather than self-applying:**

1. The router half of the false-alarm failure is still open — `tools/check_stage_ready.py` and `.claude/hooks/session-start.py` have no project concept, so a correctly onboarded member is still told their clone is broken and pointed at a framework setup path.
2. `tools/check_log_conformance.py::wrong_stream()` needs a `<ProjectName>/logs/` entry returning NA before hook chaining is even testable — **a framework checker must return NA on a path it does not govern, not FAIL.**
3. `.claude/skills/sync-downstream/SKILL.md` states that the project folder is `DESTINATION_OWNED` and aborts the sync if re-added; the array holds only case paths plus the two root documents. Per this repo's when-documents-disagree procedure, fix **every** location in ONE commit and bring the evidence to the PI.

---

## When the project has NO calibration — a first-class case, not a footnote

**Calibration is one INCLUDE decision plus one board collection, never a structural assumption.** The CORE twelve contain no calibration concept at all, and the four framework failures this skill prevents are properties of the repo topology, not of the 7-phase loop.

**When calibration IS a step,** `use_cases/` participates but **the project folder never holds a case**. Cases are authored **upstream** with `onboard-case` so they get the model's template and the two gates, then **handed over**: dropped from the leg's INCLUDE, added to `DESTINATION_OWNED`, and removed from the framework branch only after every tracked file is verified present in the destination. The handover works precisely **because** removing a path from INCLUDE does not retract the copy already delivered — the forward-only property that is a hazard everywhere else is the mechanism here. The board gains a `cases` collection that **points** at each case by path and round rather than copying its state.

**When there is no calibration, nothing about the skeleton changes.** `use_cases/` simply does not appear in the manifest, `SHIPPABLE_CASES` stays empty (both legs' policy anyway) so the allowlist guard hard-aborts on any case path rather than silently no-opping, and the calibration halves of the framework are subtracted at G4 rather than shipped and ignored.

**Rewrite the boundary rule against whatever the other half actually is.** The calibrating form is *if a calibration round's comparability or reproducibility depends on the record, it belongs to the case under `../use_cases/<Model>_<Case>/`; everything else belongs here.* For a project whose other half is a model checkout and its source overrides, the unit is that project's own reproducibility unit — a simulation's configuration, a figure's data, a dataset's citation. **Q: name that unit before writing the sentence.** Then put the sentence **verbatim in README, CLAUDE.md and ONBOARDING**, follow it with **at least six worked example rows** because the rule is easier to state than to apply, and mandate the one-line-pointer convention for work that genuinely spans both — *a pointer is cheap; a duplicated record drifts*.

**The slot calibration would have occupied is never left empty.** It is filled by the **register of the project's own unit of work** — milestones with definitions-of-done and coordination handoffs for a sponsored team project, a simulation registry generating a table refreshed from `sacct` for an ensemble-running analysis project, whose load-bearing column is *differences from the shared configuration* and whose own `check` flags a run that happened and was never registered. **Name that slot explicitly**, so a project with no calibration is not handed a hole where its actual work should be tracked.

**And make the project argue its own driver.** A calibrating project inherits the `calibration-goal` loop because that domain has a fixed sequence and a machine-checkable stopping test. A project coordinated by a deliverable contract instead needs its own next-action ranking, and the right place to argue that is the driver's own docstring.

## "What not to do here" — seed every project folder with these four

Each states its reason, not just the prohibition.

1. **Do not put a project skill in the repo root's `.claude/skills/`.** It is an INCLUDE root, so the next sync deletes it; and among fifty-odd framework skills a project skill is invisible anyway.
2. **Do not write a project memory into the root `.claude_memory/`.** It is on the leg's EXCLUDE list and speaks the framework's vocabulary; the project's bucket has its own schema and its own checker.
3. **Do not run the framework's log or memory checkers on project files.** They **FAIL rather than skip** an unrecognised stream, so a green-looking sweep here is a stream of false errors.
4. **Do not put an ignore rule in the root `.gitignore`.** The sync rewrites it wholesale on every run.

Add the project's own negatives beside them — no data in a text folder, no per-partition state file duplicating the board, no fourth partition without updating both the board and the README.

## Footguns

- **A placeholder root document passes every check there is.** `README.md`, `CLAUDE.md` and `AGENTS.md` are generated true-of-any-project and are the first thing anyone reads. No checker can tell a generic banner from a written one, `--refresh` never touches them, and their being destination-owned means nobody upstream will ever notice. Step 5b is the only thing standing between the scaffold's text and a reader.

- **The guarded leg cannot create a destination and the creating leg destroys the hooks.** Bootstrap by hand (Step 2b). Seeding with the documented tool reproduces the hook-deletion failure on run one, because the public leg lists the settings file on INCLUDE and copies it.
- **"Nothing of theirs to keep" is a FAILURE at the creation gate.** So is "their main registers only framework hooks". Both are the eight-day outage rendered as a reassuring sentence.
- **A project hook registered with the framework's path prefix is silently swept.** The merge's discriminator is the command string. Rewrite every command on adoption, then prove with M9.
- **A hook whose root resolves to `CLAUDE_PROJECT_DIR or getcwd()` PASSES after demotion.** It looks one level up, finds no directories to check, and reports success forever. M7 exists for exactly this: name what would make it fail before trusting that it passed.
- **`.git/hooks` stops running the moment `core.hooksPath` is set anywhere in the clone.** A tree that installs hooks by symlink loses its git-side enforcement **silently** on migration.
- **The generated root ignore file untracks binaries at any depth.** Unanchored `*.nc` matches inside the project folder. Prove with `git check-ignore -v`, both directions.
- **A generated ignore file narrower than the repo's own deadlocks the leg against its own dirty guard.** Superset, always.
- **Dropping a path from INCLUDE retracts nothing, an exclude retracts nothing, and a merge restores nothing.** Stopping the damage and undoing it are two actions; schedule both. A repair goes to the PR branch, never to the destination's default branch.
- **A whose-PATH review returns a true and useless answer.** Walk the manifest's SHARED-WRITE column and ask whose CONTENT.
- **A framework check that FAILs while naming a fix that breaks the project is worse than no check.** Verify the pairing before onboarding a second person.
- **Five test files enumerate the legs by literal path.** An unregistered leg leaves a green suite covering nothing.
- **A copied leg is wrong until repointed.** Seven defects in one measured instance; M3 and M4 are the gates.
- **Do not write a project skill as a backticked bare name next to the word "skill" in a framework document.** The registry contract check reads that as a framework skill reference and fails on a directory that does not exist. Write `<ProjectName>:<name>`.

## Cross-references

- `docs/40_Downstream_Project_Repo_Pattern.md` — the DESIGN this skill executes, the way `onboard-model` executes `docs/19_Adapter_Kit_Implementation_Plan.md`. Four of its statements are contradicted by practice (its naming rule, its merge-versus-rsync mechanism, its missing project-folder step, and where a case lives); Step 12 brings all four to the PI in one pass rather than silently superseding them.
- The `sync-downstream` skill — RUNS a leg that already exists. This skill AUTHORS one, repoints it, registers it in the tests and proves it once; every subsequent run is that skill's.
- `a2mc-init` (per CLONE), `onboard-model` (per MODEL), `onboard-case` (per CASE), `setup-discipline` (their definition-of-done collector, routed by `tools/check_stage_ready.py`, whose four stages have **no** project concept — so this skill carries its own definition of done and cross-references that one rather than adding a stage there).
- The `add-skill` skill — governs FRAMEWORK skills and their four-way registry parity. A project skill is directory-scoped, carries only `name` and `description`, and must never be routed through it.
- The `log` and `calibration-log` skills — the framework's streams. The project gets its own light checker precisely because the framework's fails rather than skips an unrecognised one.
- `scripts/wrap_for_project_agent.sh` — the mechanism: `--init` builds a destination, `--refresh` keeps it current, and it refuses a development clone as its source.
- `scripts/_wrap_scaffold.sh` — the project half, generated rather than copied from a donor.
- `tools/check_clone_setup.py`, `scripts/setup_clone.sh`, `tests/test_clone_setup_project_hooks.py` — the worked example of a framework check taught to ACCEPT a project's arrangement while still failing five negative cases.

