# Getting and building ATS

The one place A2MC records how to get ATS's source and build a working binary. `a2mc-init` Step 2
sends a user here when there is no built ATS on the machine.

> **Status, 2026-09-23: the ATS adapter is not finished onboarding.** It registers and its
> parameter and output parsers work, but it has no knowledge-profile milestone, no model memory
> store and no run template on this line, so `model_preflight` reports **NO MILESTONE** (exit 2)
> for any ATS checkout. A calibration case on ATS first needs the `onboard-model` skill to resume
> the adapter at its first failing row (`python3 tools/check_stage_ready.py --model ats`). No
> A2MC-tested build recipe exists yet.

## Source and build

ATS is not built on its own: it is built as part of **Amanzi**, and ATS's own `INSTALL.md`
redirects to Amanzi's instructions, `https://github.com/amanzi/amanzi/blob/master/INSTALL_ATS.md`.
Do not run `cmake` inside the ATS tree; it needs Amanzi's build system and third-party libraries.

- ATS commit the adapter's knowledge base describes: `42b0e940` (`ats-1.7-dev-22-g42b0e940`).
- The binary a case runs is set in its site config as `A2MC_ATS_EXE`.

## When a build succeeds

Record the Amanzi and ATS commits, the toolchain and the machine here, archive the binary with
`tools/model_archive_build.sh` (ATS builds into a shared tree like EcoSIM and PFLOTRAN), and bind
`A2MC_ATS_EXE` to the archived copy.
