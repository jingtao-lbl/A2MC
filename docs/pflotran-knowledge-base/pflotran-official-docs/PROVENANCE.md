# Provenance — PFLOTRAN Official Documentation

**Added:** July 30, 2026
**Added by:** Jing Tao with Claude
**Branch:** A2MC-adapter-kit-PFLOTRAN

---

## What this is

A verbatim copy of the **upstream PFLOTRAN documentation source repository** — the reStructuredText that builds <https://documentation.pflotran.org/>. This is the Tier-1 "Static Documentation" layer for PFLOTRAN, mirroring `docs/fates-knowledge-base/fates-official-docs/` for FATES.

It is the *upstream* docs. It is **not** the A2MC-generated codebase wiki (that will land separately at `pflotran-codebase-wiki-<commit>/` once a source commit is pinned — see `memory/dev_logs_adapterkitpflotran/20260730c`).

## Source

| | |
|---|---|
| Upstream | `https://bitbucket.org/pflotran/pflotran-documentation.git` |
| Branch | `master` |
| Commit | `c7e121aa2c42d38a17c0fda8d914615b8abf8bba` |
| Commit date | 2026-07-17 16:02:21 +0000 |
| Commit subject | `Merged in rosie/update-cpr-extraction-type-keywords (pull request #192)` |
| Retrieved | 2026-07-30 |
| Copied | verbatim, `rsync -a --exclude='.git/'` — **no edits**, nested `.git/` stripped |

Note this is the **documentation** repo, a *separate* repository from the PFLOTRAN **source** repo (`bitbucket.org/pflotran/pflotran`). Their commits are unrelated and advance independently — do not confuse the two hashes.

## Licence

**GNU LGPL v3**, Copyright Battelle Memorial Institute. The upstream `LICENSE` and `COPYRIGHT` files are retained here alongside the content, which is what redistribution requires. Keep them with any copy.

## Contents

| Path | RST files | What |
|---|---|---|
| `source/user_guide/` | 121 | Input-deck card reference, how-to guides, examples. **The most directly useful tier for the adapter's parameter parser** — it documents the deck keywords the parser must address. |
| `source/theory_guide/` | 25 | Governing equations, flow modes, reactive transport formulation |
| `source/developer_guide/` | 10 | Build, testing, configuration-management plan (incl. the release/versioning scheme) |
| `source/qa_tests/` | 1 | QA test descriptions |
| `.deprecated/`, `.gitlab/`, `tools/` | — | Upstream ancillary content, retained for fidelity |

311 files, 14 MB.

## Refreshing

Re-clone and re-copy, then update the commit fields above:

```bash
git clone --depth 1 https://bitbucket.org/pflotran/pflotran-documentation.git /tmp/pfdocs
rsync -a --delete --exclude='.git/' /tmp/pfdocs/ docs/pflotran-knowledge-base/pflotran-official-docs/
cd /tmp/pfdocs && git log -1 --format='%H %ad' --date=iso   # record this
```

Use `--delete` so upstream removals propagate; re-add this `PROVENANCE.md` afterwards (it is ours, not upstream's).

## Public sync

`scripts/sync_to_public.sh` and `scripts/sync_adapterkit_to_public.sh` carry an **explicit allowlist** of knowledge bases (`docs/fates-knowledge-base/`, `docs/elm-knowledge-base/`) rather than a `docs/*-knowledge-base/` glob. So this directory does **not** currently ship to any public repo — the same status as `docs/ecosim-knowledge-base/` and `docs/ats-knowledge-base/`. If PFLOTRAN is ever added to a public release, add the path to those allowlists deliberately, and keep `LICENSE` + `COPYRIGHT` in place when doing so.

## Deviation from the FATES layout

`fates-official-docs/` has no provenance file, so its upstream commit is unrecorded. That is a gap, not a pattern to copy — this file exists so the docs tier is as identifiable as the commit-pinned wiki tier. Consider back-filling the FATES one.
