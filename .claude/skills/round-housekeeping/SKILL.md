---
name: round-housekeeping
visibility: public
category: calibration
description: Run the POST-ROUND housekeeping — the step between one round's human gate and the next round's Phase 0, and the one nothing used to schedule. Curate the round's Phase-5-verified findings into the site knowledge base, promote or discard the online agent's staged proposals, record the case's script templates, emit the open-questions list the next round's design must answer, record which bounds are still provisional debt, and ASSERT the knowledge base is non-empty where the round produced findings. Use when the user says "run the housekeeping", "close out the round", "curate this round's knowledge", "what did we learn this round", or when `resolve_next_action()` returns `close("housekeeping")`. A CONVERGED round runs this too, with a FULLER checklist — see the campaign-close section. DISTINCT from summarize-calibration-round / write-report (the round's REPORT, which runs BEFORE the gate) and from curate-knowledge (one of the steps this skill sequences).
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [calibration, memory]
  summary: "Post-round curation between the gate and the next Phase 0; model-agnostic. Fuller on convergence."
---

# Round housekeeping (after the gate, before the next Phase 0)

**The gap this closes, measured.** After **three calibration rounds and thirty experiment cycles**, one case's site knowledge base held `experiments: []`, `failed_approaches: []`, `parameters: {}`, and its newest write predated that round's Phase 0 entirely. `calibration-discipline` items 11 and 12 described the promotion correctly, but **a checklist is not a driver**: `resolve_next_action()` routed a cleared gate straight to `run_phase("design")`, so there was no state position where housekeeping could be scheduled and it fired only if someone remembered. Every finding that would have prevented that round's four repeated errors belongs in those empty files.

**This skill SEQUENCES and VERIFIES. It does not re-specify.** The procedures already exist — `phase6-refinement` Step 3 carries the knowledge-write routes and Step 3b the script promotion. A third copy would be a fourth place for them to drift. What did not exist is anything that runs them in order and then checks the outcome.

## Where this sits

```
Phase 6  ──▶  close(round_close)  ──▶  ⛔ HUMAN GATE  ──▶  close(housekeeping)  ──▶  Phase 0 (next round)
              the three report                              THIS SKILL              or Phase 7 CONVERGED
              steps, in order
```

**Before the gate: the report. After the gate: this.** The order is not cosmetic. Curating knowledge is a **Tier-3 curated write**, one of the four human gates (`calibration-goal` gate 2, `calibration-discipline` item 11: *"both human-gated Tier-3 writes, so they happen at / after the gate, not before"*). Running it earlier would put a human-gated write ahead of the human gate.

`resolve_next_action()` returns `close("housekeeping")` and the driver executes it — **it is not itself a gate to surface**, because the gate it follows has already cleared.

## The checklist

Work these in order. Each dispatches to the skill or tool that owns the procedure.

1. **Curate the round's VERIFIED findings into the site knowledge base.** Only findings a Phase-5 test actually verified this round — never a mechanism story (`feedback_no_kb_injection_before_verified_test`). Destination is the case's own store, `use_cases/{Model}_{Case}/memory/gained_knowledge/`, **not** the generic one.
   - a finding **you** originated → [`inject-knowledge`](../inject-knowledge/SKILL.md)
   - **Record every refutation as its `(parameter, direction, base)` triple with its mechanism.** A refutation is a property of that triple, not of the parameter: a dose that moved monotonically the wrong way is positive evidence for the opposite direction, not a closed door. Recording only the parameter name is how a lever gets written off on one round's evidence.
2. **Promote or discard the online agent's staged proposals**, and **record what was discarded and why**. → [`curate-knowledge`](../curate-knowledge/SKILL.md) (`tools/review_pending_knowledge.py`). A discard with no recorded reason is re-proposed next round.
3. **Review script promotion.** → `phase6-refinement` Step 3b, which carries both routes and their `tools/promote_diagnostic_script.py` invocations. **The case's own `scripts/` templates are RECORDED, not auto-promoted** — reuse across one site's rounds is evidence a script is reusable *for that case*, not that it generalizes across models (PI, 2026-08-22).
4. **Emit the OPEN-QUESTIONS list.** The ROUND report enumerates the questions; this step carries them forward as a named artifact with a path, so the next Phase 0 has an input rather than just a cleared gate. Each item needs **what would settle it** and **what it blocks**. Write it beside the round report and record the path in the state.
5. **Record the round's BOUND DEBT.** Which rows still carry a `provisional:` `bound_source`, and which the round's own evidence now permits refining. `python tools/check_bound_source.py <the round's param list>` lists them; a `provisional:` bound byte-identical to the previous round's is flagged as carried-not-paid. Measured cost of skipping this: one round ran 15 of 28 bounds on an unread deferral, and four of the six parameters whose lethal ranges killed 81% of that ensemble were among them.
6. **ASSERT the knowledge base is non-empty where the round produced findings — ALL FOUR STORES, plus the run ledger.** The one check that would have caught thirty cycles of silence.
   ```python
   from memory import MemoryManager
   m = MemoryManager("use_cases/{Model}_{Case}/memory/gained_knowledge")
   print(m.stats())   # discoveries / experiments / parameters / failed_approaches
   ```
   `stats()` prints all four. **State the failure condition for each of them, not just for one** — until 2026-09-08 this step named `failed_approaches` alone, so a round could pass it holding nine recorded refutations and `experiments: []`, which is exactly the state one case was in:

   | store | it is EMPTY and the round is not | because |
   |---|---|---|
   | `experiments` | any experiment cycle ran | one entry per cycle: the hypothesis, what was executed, the outcome class, the lesson. This is the **interpreted** record; the raw per-simulation record is the ledger below |
   | `failed_approaches` | any hypothesis was REFUTED | one entry per `(parameter, direction, base)` triple, per step 1 |
   | `discoveries` | any mechanism was CONFIRMED and Phase-5-verified | a diagnosis is not a discovery until a test verifies it ([[feedback_no_kb_injection_before_verified_test]]) |
   | `parameters` | the round measured a bound, a sensitivity or an inert lever | a parameter shown to be gated off at this case is knowledge, and a costly thing to rediscover |

   A round that refuted levers and recorded **zero** `failed_approaches` did not curate — it skipped step 1. The same reading applies to each row. Say so and go back rather than recording the housekeeping as done.

   **And check the RUN LEDGER separately, because it is a different kind of object.** `use_cases/{Model}_{Case}/memory/run_records.json` is the per-simulation record — case, cycle, status, job id, parameter values, scores — written automatically by Phase 5 as the runs progress. It is **ungated**: nothing in it is a claim, so it needs no curation and housekeeping does not fill it. What housekeeping does is **notice if it is short**, since a gap there means a Phase 5 did not record and the round has lost what it ran:
   ```bash
   python tools/record_run_status.py list --case-dir use_cases/{Model}_{Case} --round <R>
   ```
   Compare the count against the round's cycles and the cases each one submitted. `check_offline_log_evidence.py` warns per phase-5 log when a submitted case is missing from it, so a clean pre-commit run is the cheaper check; this step is the round-level total.
7. **Record it in the state**, so `check_workflow_state_offline.py` can see it happened:
   ```python
   st.set_housekeeping(kb_curated=True, scripts_reviewed=True,
                       open_questions_path="...", bound_debt_recorded=True)
   st.save()
   ```

## On CONVERGENCE the checklist gets FULLER, never shorter

**PI decision, 2026-08-25**, answering against the recommendation on record at the time. It is tempting to skip the forward-looking items when there is no next round to prepare. That is backwards: **convergence is the CAMPAIGN boundary, not a round boundary.** A mid-campaign round hands work to the next round, and anything it drops gets caught later. A converged close hands work to **nobody** — every omission is permanent and every deferral silently becomes a limitation of the published result.

So all seven items above still run, and these six are **added**:

- **C-1 — record the FINAL CONFIGURATION as a reproducible artifact.** Parameter values, the base file they modify, the case that achieved them, the **archived** model binary (never the live build path — a queued job resolves its exe at run time, `feedback_bind_runs_to_archived_binaries`), and the command that reproduces it, **plus the INPUT BUNDLE copied in** — every file the run reads, under `inputs/`, with a `MANIFEST.md5`. This is the campaign's actual product, and nothing else in the workflow specifies it. **Copy, do not point:** measured 2026-09-09, a converged campaign's four forcing files sat under a `.gitignore`d directory, so no clone of the repo held the drivers and the campaign was unreproducible from its own record while every path in it was correct. The bundle doubles as the tar handed back to the contributor who supplied the measurements. Full specification, including the executable-by-reference rule and the repointing recipe: [`phase6-refinement`](../phase6-refinement/SKILL.md), element 7.
- **C-2 — evaluate every site discovery for GENERALIZABILITY and promote what qualifies** into the case's own **model** store: `memory/gained_knowledge/` for a FATES case (unprefixed, because FATES predates the per-model layout), `memory/<model>/gained_knowledge/` for an EcoSIM or PFLOTRAN case. This judgement is only answerable now: what generalizes is what survived, and what survived is not known until the campaign converges.
  ```bash
  python tools/promote_knowledge.py --list                                  # what the site store holds
  python tools/promote_knowledge.py --name X --rationale "why it generalizes" --dry-run
  ```
  **Per discovery, never in bulk — there is no `--all`.** "Generalizes beyond this site" is a scientific judgement the tool cannot make and does not try to; it refuses a promotion with no `--rationale`, one whose discovery is unverified, and one that would overwrite an existing model-store entry. It **copies**, leaving the site entry as the record of where the finding came from, and **caps the promoted confidence at 0.7**, because one site is one observation of generality. **It never writes one model's finding into another model's store:** the model comes from the case's own config declarations (a FATES case declares none), and it refuses when those declarations disagree, when a sourced `$A2MC_MODEL` names a different model, or when the model has no store to promote into.
- **C-3 — discharge or DECLARE the bound debt.** Every bound still `provisional:` at convergence is a range the accepted values sit inside without justification. There is no next round to refine it in: refine it, or state it as a limitation of the result.
- **C-4 — report against data that was NEVER SCORED.** `targets.yaml` is calibration-only and validation data is not scored (`reference_calibration_vs_validation_data_taxonomy`). Mid-campaign this would leak validation data into calibration; at the terminal it is the result's credibility.
- **C-5 — close the cross-round ledger as a CAMPAIGN ledger** — every parameter's final disposition across all rounds, not a two-round comparison.
- **C-6 — state the campaign's RESIDUAL.** What was not achieved, routed to model development or to data, so the next person does not rediscover it as a surprise. The redesign loop normally carries this forward; convergence has no loop to carry it.

## Known gaps (do not paper over these)

- **C-2's executor is new and unexercised.** `tools/promote_knowledge.py` was written 2026-08-25 to close an arrow the root project instructions had documented with **no implementation at all** — no tool, no `MemoryManager` method, no skill step. It has tests but **no campaign has converged yet**, so it has never run on a real promotion. Treat its first use as the test it has not had, and read the diff before committing. Until 2026-09-11 it also wrote every promotion into the FATES store (`memory/gained_knowledge/`) whatever model the case ran, which would have misrouted the first converged non-FATES campaign's promotions; it now routes each one to the case's own model store (`memory/dev_logs_adapterkit/20260911b_The_Promotion_Tool_Wrote_Every_Case_Into_The_FATES_Store.md`).
- **The Phase-7 final configuration gained its contract on 2026-08-25** (it had none: three skills stated the deliverable in the same seven words and nothing said what the artifact was). C-1 above is now the *checklist item*; the *specification* — seven required elements (the seventh, the copied-in input bundle, added 2026-09-09), its location, and the state pointer a checker asserts — lives in [`phase6-refinement`](../phase6-refinement/SKILL.md) under "The Phase-7 CONVERGED deliverable". Follow that; do not re-derive it here.

## Cross-references

- **Reciprocal skills** — `calibration-goal`, `phase6-refinement`, `curate-knowledge`, `inject-knowledge`: the driver that dispatches this step, the phase whose Step 3 and Step 3b own the procedures it sequences, and the two curated-write skills it routes to. Each names this skill back.
- [`calibration-discipline`](../calibration-discipline/SKILL.md) — items 11 and 12 are this skill's checklist in its original checklist form; they now point here rather than restating the procedure.
- [`phase0-design`](../phase0-design/SKILL.md) — "Opening a NEW round" consumes the open-questions artifact this step emits.
- `tools/check_workflow_state_offline.py::_check_round_close` — the mechanical half: it reports a closed round whose housekeeping was never recorded.
- `tools/check_bound_source.py` — step 5's instrument.

