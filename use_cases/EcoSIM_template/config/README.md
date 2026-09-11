# `config/` — the site-level configuration, what a session SOURCES

**Everything here is live configuration a working session depends on** — not notes about configuration. Two kinds:

| file | what it is |
|---|---|
| `<model>_<case>_config.sh`, and any `_r<N>.sh` round wrapper | **sourced** — shell, read into the environment |
| `calibration_rounds.yaml`, `binary_archive_manifest.json` | **read by tools**, never sourced; both are GENERATED, then partly filled by the agent |

Nothing here is documentation-about-the-case; that belongs in the case README or a phase log.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| **running anything at all** — the source order below is step 0 of it | **`ecosim-run-workflow`** |
| opening a round (writing `_r<N>.sh`) | `phase0-design` |
| adding a model-binary entry to the ledger | `model-evolution` (step 3.5) |
| archiving a binary, or checking one has not been swapped | `model-evolution` (step 3.5) + `tools/binary_archive_manifest.py` |
| creating a case from scratch | `onboard-case` |

## The source order: ONE command

```bash
source use_cases/EcoSIM_template/config/<site>_config.sh          # or the round wrapper, <site>_config_r<N>.sh
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

## `binary_archive_manifest.json` — the record of binaries git cannot hold

**A run must bind to an ARCHIVED, content-addressed executable, never to the live build path.** EcoSIM has **one** build output; every rebuild overwrites it in place; and a queued scheduler job resolves its executable at **run** time. So a rebuild between submit and start swaps the model under a running ensemble and nothing reports it — the run does not fail, it just silently answers for a different model than you think. This has cost real work more than once, including a whole invalidated parameter null.

The archives themselves cannot go in git: ~25 MB each, and putting them in a fork of an upstream scientific code bloats its history permanently. They are also **not regenerable** — a recompile can perturb floating point, so a rebuilt binary is a *different* artifact, not the same one recovered. Git tracks this **manifest** instead: a few KB giving, per archive, its label, source commit, size and SHA256. That is enough for the three things tracking was for — a permanent record that each binary existed, a checksum to detect alteration or swap, and enough provenance to say which build produced a result.

### It is GENERATED, never hand-authored

```bash
python tools/binary_archive_manifest.py --generate --model ecosim   # scan the archive dir, refresh
python tools/binary_archive_manifest.py --verify   --model ecosim   # check disk against it
```

`--generate` reads each archive directory and the `PROVENANCE.txt` inside it. **A hand-typed SHA256 is an assertion nobody can check**, which is the exact problem the file exists to remove. What you write by hand is the `PROVENANCE.txt` at archive time; the manifest is derived from it.

### What makes `--verify` FAIL

Named before the command is trusted, because a check whose failure mode nobody can state is not a check:

| | condition | |
|---|---|---|
| M1 | an archive in the manifest is **missing** from disk | ERROR |
| M2 | a binary's SHA256 **differs from the manifest** | ERROR — altered or swapped |
| M3 | a binary's SHA256 differs from **its own `PROVENANCE.txt`** | ERROR — internally inconsistent |
| M4 | an archive is on disk but **absent from the manifest** | WARN — re-generate |
| M5 | an archive directory has no binary, or no `PROVENANCE.txt` | WARN |
| M6 | **no archive root at all** | ERROR — the anti-silent-pass: an empty run is a failure, not a pass |
| M7 | a `round_binaries` checksum claim in `calibration_rounds.yaml` does not resolve against the manifest | ERROR |

M7 is the link that makes the whole chain checkable: **archive → manifest → `round_binaries` → `--verify`**. Without it, a round record can name a binary that no longer exists, or never did.

### The manifest is PER-MODEL, so this copy stays empty

**Read this before expecting a scaffolded case to fill its own.** One EcoSIM build archive is shared by every EcoSIM case, so the live manifest is keyed by **model**, and its path is hardcoded in `tools/binary_archive_manifest.py::ARCHIVES`. Two consequences:

- **Scaffolding a case does not register a manifest.** `--generate` writes to the path already in `ARCHIVES`; it will not write into a new case's `config/`. This template copy is therefore inert — nothing reads it, because the tool only ever opens the registered path.
- **It ships with `"archives": []` on purpose.** A template carrying a filled-in list would make every scaffolded case assert checksums for binaries it never built. Empty is the honest state; the file is here to teach the shape and the commands, and `_example_archive` shows one entry with a deliberately **invalid** placeholder SHA so it cannot be mistaken for real.

If a case ever genuinely needs its own manifest — a private archive root, a different machine — that is a change to `ARCHIVES`, not a file you can drop into `config/`.

### ⚠ Open defect in this template: the config still points at the live build path

`<model>_<case>_config.sh` currently exports

```bash
export A2MC_ECOSIM_BINARY="${A2MC_MODEL_PATH}/build/Linux-x86_64-double-Release/bin/ecosim.f90.x"
```

which is the live, mutable path this whole section exists to prevent — so **every case scaffolded from this template starts bound to it by construction**. Until the template is fixed, repoint it before materializing any ensemble:

```bash
export A2MC_ECOSIM_BINARY="<archive_root>/<LABEL>/ecosim.f90.x"
sha256sum "$A2MC_ECOSIM_BINARY"      # must match the manifest entry for <LABEL>
```

Archive the binary **immediately after the link step**, before running anything with it — an archive taken later cannot prove it is the build that ran.

## Verify before trusting

```bash
python tools/check_setup_ready.py                                   # the config chain resolves
python tools/binary_archive_manifest.py --verify --model ecosim     # the archives are intact and unswapped
```
