# `memory/gained_knowledge/` — the curated knowledge base, and the gate in front of it

**A promoted entry is not a result. It is an instruction to every future round**, injected into the reasoning context of every subsequent diagnosis. That is why writing here is one of the four human gates.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| **reviewing and promoting staged proposals** | **`curate-knowledge`** |
| injecting a human-originated discovery | **`inject-knowledge`** |
| the post-round curation pass | **`round-housekeeping`** |
| the cycle that produced the candidate | `phase6-refinement` |

## The write gate: online proposes, offline disposes

- The **autonomous** agent runs `MemoryManager` in `propose` mode. Its findings are staged to `auto_discovered_pending.json` — gitignored run-state — and it **cannot** write here.
- The **interactive** agent reviews and promotes, with a human in the loop:

```bash
A2MC_USE_CASE_DIR=use_cases/ELM-FATES_template python tools/review_pending_knowledge.py list
A2MC_USE_CASE_DIR=use_cases/ELM-FATES_template python tools/review_pending_knowledge.py promote --key ... --verified-by ...
```

**Never edit the curated JSONs by hand.** The staging file is where a candidate belongs until a human says otherwise.

## What an entry must carry before it is promoted

- **The `(parameter, direction, base)` TRIPLE.** A refutation is a property of that triple, not of a parameter name. Getting the direction wrong makes `check_do_not_repeat()` match the wrong thing.
- **`verified_by`** naming the log, report or run that establishes it.
- **A mechanism that was measured, not inferred.** A mechanism read off the source and never tested is a hypothesis wearing a citation.
- **Its scope.** "At this base", "in this range", "on this binary" belong in the entry.

## What is here

`discoveries.json` · `experiments.json` · `parameters.json` · `failed_approaches.json` — site-specific, hand-vetted. Generic framework-level knowledge lives at the repo root in `memory/gained_knowledge/`.
