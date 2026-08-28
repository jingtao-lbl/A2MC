# `config/` — the site-level configuration, what a session SOURCES

**Everything here is live configuration that a working session sources.** A file in this folder should be one you might legitimately source today.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| **running anything at all** — the source order below is step 0 of it | **`ats-run-workflow`** |
| opening a round (writing `_r<N>.sh`) | `phase0-design` |
| adding a model-binary entry to the ledger | `model-evolution` (step 3.5) |
| creating a case from scratch | `onboard-case` |

## The source order: ONE command

```bash
source use_cases/ATS_template/config/<site>_config.sh          # or the round wrapper, <site>_config_r<N>.sh
```

Since v2.306 **the site config auto-sources the machine config** — `a2mc_noncime_config.sh` for this model — when one is not already loaded, and **repairs the wrong one** if it was sourced by mistake. Sourcing the machine config first still works and is a no-op. Order is unchanged: machine defaults, then site overrides, then a round wrapper's overrides.

**Check rather than assume.** The three loop limits live in the machine config and nowhere else, so they are the signal that the chain resolved:

```bash
echo "$A2MC_MAX_EXPERIMENTS $A2MC_MAX_SKIP_TESTING $A2MC_CONFIDENCE_THRESHOLD"   # none empty
```

## `calibration_rounds.yaml` — generated first, then filled by the agent

| when | what | who |
|---|---|---|
| opening a round | generate the block, then fill `rationale` / `changes_from_previous` | `phase0-design` |
| creating the case | generate round 1 **last**, after the parameter list exists | `onboard-case` |
| a model source change lands | one `model_change_ledger` entry | `model-evolution` supplies it |
| closing a round | `outcome`, `round_binaries`, `comparability` | `summarize-calibration-round` |

Derive it, never hand-author it:

```bash
python scripts/generate_adapter_calibration_rounds.py --round N --write
python scripts/check_adapter_calibration_rounds.py
```

**The `comparability` block is the point of the file** — it is what makes a cross-round comparison honest, and nothing else in the case records it.

## Verify before trusting

```bash
python tools/check_setup_ready.py            # the config chain resolves
```
