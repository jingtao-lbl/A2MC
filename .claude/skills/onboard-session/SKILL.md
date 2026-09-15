---
name: onboard-session
visibility: public
category: meta
description: Cold-start runbook — orient at the start of a session or after a context reset/compaction. Use when a session begins, resumes, or is compacted (especially if the SessionStart snapshot shows in-flight work or pending proposals), or when the user says "catch up", "where did we leave off", "onboard", "what's the current state". Reads the latest calibration log and the case's offline workflow state, re-reads CLAUDE.md, checks live HPC processes + run state, and hands off to arm-hpc-monitoring / curate-knowledge as needed.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [session]
  summary: "Cold-start session runbook; model-agnostic."
---

# Onboard a Session (cold-start runbook)

The interactive agent often starts cold — a fresh session, a resume, or after compaction. This skill is the checklist that restores full context and catches in-flight work before you act. It **pairs with the G2 `SessionStart` hook** (`.claude/hooks/session-start.py`), which already surfaces a snapshot (branch, uncommitted count, latest handoff, pending-knowledge count, live processes). The hook gives the *data*; this skill is what you *do* with it.

> Run this whenever the snapshot shows in-flight work, after a compaction, or when the user asks you to catch up. Skip the HPC steps if no ensemble is active.

## Step 1 — restore context

1. **Re-read `CLAUDE.md`** (root). Required after compaction (memory: `re-read CLAUDE.md after compaction`) — it carries the branch banner and the operating rules. Don't reconstruct the knowledge system from `AGENTS.md`'s one-liner — `CLAUDE.md` §"RAG/GraphRAG System" (+ `docs/a2mc_reference/rag_reference.md`) carries the full hybrid vector + two-layer knowledge graph + curated YAML detail.
2. **Verify branch:** `git branch --show-current` → confirm it matches your intended working branch (`main` or your feature branch). `git status -s` for uncommitted work the previous session left.
3. **Read the latest calibration log and round/cycle report** — the SessionStart snapshot lists the most recently CHANGED of both across the clone's cases; else, newest-touched first: `ls -t use_cases/*/memory/logs/*.md use_cases/*/reports/*/*.md | grep -v README | head`. Narrow to the active case once you know it. A round or cycle **report** is usually the fastest single read for where the calibration campaign stands; the **phase logs** carry the finer-grained trail, so read the report first and the logs for detail. Read for open threads and the `## Next` section; skim the 2–3 most recent for anything still mid-flight. Sorting by mtime rather than by the filename date is deliberate: a file revised today still surfaces even if its stem is older.
4. **Read the offline resume brain** (docs/31/34) — the SessionStart snapshot prints an `Offline state:` line from the highest-round `workflow_state_offline_r{RR}.json` (position + `next_action` + any `phase6_decision` binding target). If a round is mid-refinement, note the **binding target + next targeted experiment** — that is the objective to drive toward (`feedback_performance_experiment_is_the_objective`), not the loudest crash thread. **Validate it:** the SessionStart hook flags a corrupt state (`⚠ Offline state INVALID …`); if it does, run `python3 tools/check_workflow_state_offline.py` and fix the invariants before driving.
5. **Recall the operating discipline.** Skim `AGENTS.md` §"Offline-Agent Operating Discipline" — the four recurring failure modes (verify before claiming · track the objective · drive, don't wait) and the gate enforcing each. Lead memory: `feedback_offline_agent_operating_discipline`.

## Step 2 — check for in-flight HPC work

```bash
ps -ef | grep "$USER" | grep -E 'monitor|submit|extract' | grep -v grep
```
- **If an auto-monitor / submitter / extractor is running** → an ensemble is in flight. Invoke the **`arm-hpc-monitoring`** skill (CLAUDE.md Rule 6) to arm `Monitor` on the live logs with the event + error filters. Read the active handoff log for the round-scoped event names/filenames.
- **Check run state** if a round is active: `squeue -u "$USER"` (or the round's job prefix) and, for completion, `tools/diagnose_ensemble_status.py`. Re-derive counts from live `squeue` + disk NC counts + the most recent dated log (memory: `verify run-state before quoting`) — don't trust stale numbers in an old log.

## Step 3 — check pending knowledge

If the snapshot reports pending proposals (or `use_cases/*/memory/gained_knowledge/auto_discovered_pending.json` has open items), invoke the **`curate-knowledge`** skill to review + promote/discard them. Online runs stage proposals here; they only enter the curated KB when a human-in-the-loop session curates them.

## Step 4 — drive the next action, don't wait (docs/35)

Close the onboarding by **advancing the workflow**, not with a bare readout. When the offline resume brain (`workflow_state_offline`) holds an active goal + a `next_action` (the SessionStart `► NEXT:` line), **execute it** — you are the superset of the autonomous orchestrator, which drives itself with no per-phase prompt ([[feedback_offline_agent_drives_the_workflow]]). Lead with: *"Round R{N}, phase X; next action = `<...>`. Proceeding with it — will pause only at a fork or hard stop."* Then do it.

> **To drive the *whole* calibration to the goal (not just this one action), hand off to `calibration-goal`** — the run-to-convergence driver that loops this drive-the-next-action over the full 7-phase workflow (via `resolve_next_action`) until Phase-7 CONVERGED or a loop limit, pausing only at the gates. `onboard-session` orients + resumes; `calibration-goal` drives.

**DRIVE (just do it — surface results, not permission requests):**
- arm/re-arm monitors; extract completed data; run a **planned** experiment; skip-test on existing data; advance to the next phase per the 7-phase workflow + iteration rules; regenerate a plot; commit routine work.

**PAUSE for the human (a genuine fork or hard stop):**
- a **Phase-6** converge / redesign / **stop→model-dev** decision (the `docs/34` objective gate — a hard pause);
- a **curated-KB write** (`inject-knowledge` / `curate-knowledge` promote — Tier-3, human-gated);
- an **expensive / irreversible** action (a full-ensemble redesign, a large HPC spend, anything hard to undo);
- the standing hard stops: destructive / outside-repo actions, a claim about the user, an ambiguous instruction.

Everything not in the PAUSE list, you drive. Surface **proposals + results**, not "shall I…?" for mechanical steps.

## What this skill does NOT do
- It does not replace the **G2 SessionStart hook** (that runs automatically and surfaces the snapshot); this skill acts on it.
- It does not arm monitors itself — it delegates to `arm-hpc-monitoring`.
- For the full monitoring reactions, invoke the `arm-hpc-monitoring` skill (required when an ensemble is in flight, per CLAUDE.md Rule 6).

