# `scripts/` — the case's canonical script TEMPLATES

**Nothing here is run in place.** Every file is a **template**: copy it into the phase's own `memory/phase_results/{stem}/` and adapt it there. The adapted copy is the canonical script for that figure or analysis and ships beside its caption and data.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| **before the first `savefig`** — not after | **`plotting`** (its load-bearing rule is to open the rendered PNG and look at it) |
| copying a template into a phase folder | that phase's own skill, `phase0-design` … `phase6-refinement` |
| running or submitting anything | `offline-testing-workflow` |
| deciding whether a script has earned promotion to here | **`calibration-discipline`** item 2b |
| watching a submitted set | **`arm-hpc-monitoring`** |

## The three-tier rule, which is why this folder exists

```
scripts/                        the canonical script TEMPLATE      (seeded at onboarding)
        │  copy into the phase's folder, then ADAPT for that phase's purpose
        ▼
memory/phase_results/{stem}/    the canonical SCRIPT for this figure, beside its
                                caption, data and notes — this is the log's evidence
```

1. **Look here first.** If a template covers what the phase needs, copy it into `phase_results/{stem}/` and adapt it there. Do not run it from this folder, and do not edit the template to suit one phase.
2. **No template? Write one from scratch** in the phase folder. That is the correct first-use state.
3. **A script's SECOND use is the trigger** to promote it here, then copy it back and adapt. Second, not third.

`tools/check_case_script_tier.py` (pre-commit 15, WARN) flags a duplicated script.

## Adapting a template

Keep the docstring's WHAT-IT-OWNS section and rewrite the CONFIG block. State in the adapted copy what you changed and why — particularly if you deliberately break one of the template's assertions, because the next reader will otherwise treat it as the bug the assertion exists to catch.
