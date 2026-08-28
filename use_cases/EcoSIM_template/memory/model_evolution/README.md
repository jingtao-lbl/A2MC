# `memory/model_evolution/` — changes to the MODEL's source, and which round ran which binary

**This is model evolution, triggered by a bug surfacing or a model-development need.** Tuning a value in a parameter file is Phase 0/5. Changing *what the code does* — a mechanism, a loop, a cap, a new parameter's wiring — is model evolution, and it is recorded here, under the case that runs it, so the mechanism and its effect on the calibration read together.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| **any change to model source** | **`model-evolution`** — read the model checkout's own `CLAUDE.md` §1 first |
| writing the record | **`log`** |
| the round-close entry naming the binary | **`summarize-calibration-round`** |
| the calibration cycle that motivated it | `phase4-hypothesis`, `phase5-testing` |

## The rules that are not negotiable

1. **Earn it.** Model development comes after the calibration loop is provably exhausted, not instead of it.
2. **Mechanism first.** Verify on existing data that the mechanism can move the target before paying for a structural change. Wiring is easy; the control point is where it fails.
3. **PRESERVE THE BASELINE BEFORE YOU BUILD.** EcoSIM builds into a shared CMake tree -- `build/<config>/bin/ecosim.f90.x` is ONE file every build overwrites in place. Archive the current binary with its SHA256 and a `PROVENANCE.txt` *first*, **then record it**: `python tools/binary_archive_manifest.py --generate --model ecosim`.
4. **Bind runs to the ARCHIVE, never the live path.** A queued job resolves its executable at **run** time, and the rebuild that swaps it need not be yours.
5. **Switch-gate default-off**, and prove the switch-off build reproduces the baseline bit-for-bit.
6. **Verify by ARTIFACT, never exit status.** An `exit 0` from a script that never ran looks identical to success.
7. **`!Jing Tao:` comment on every edited line** — mechanism, units, value choice, follow-ups.
8. **Push to the `fork` remote ONLY**, never upstream.

## Why this folder matters even when no source changed

`../../config/calibration_rounds.yaml` records **which binary each round ran** and the comparability verdict between rounds. That ledger is what makes a cross-round comparison honest, and the claim is checkable:

```bash
python tools/binary_archive_manifest.py --verify     # M7 resolves each round's sha256_prefix
```

## What is here

Stems `YYYYMMDDx_model_evolution_r{RR}_{descriptor}.md`, sorting and cross-referencing exactly like a phase log.
