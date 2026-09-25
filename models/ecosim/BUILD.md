# Getting and building EcoSIM

The one place A2MC records how to get EcoSIM's source and build a working binary. `a2mc-init` Step 2
sends a user here when there is no built EcoSIM on the machine; `onboard-case` Step 2 then binds a
case to the archived binary. Update this file in place when the recipe changes, and keep the
**Last verified** line honest.

**Last verified:** Perlmutter, 2026-07-11 (this recipe, GCC 13.2.1, at upstream `2dea74d9`) and
2026-08-22 (the fork's `main` line, archived as `V0change_mergedmain_3ffe0f57`). Not yet verified on
macOS.

## Which source to build

| source | what it is | what `model_preflight` says |
|---|---|---|
| `https://github.com/jingtao-lbl/EcoSIM`, branch `main` | a public fork, the line A2MC's own EcoSIM cases build from | **DRIFT** (exit 3): proceed |
| `https://github.com/jinyun1tang/EcoSIM` at `2dea74d9` | upstream, the commit A2MC's EcoSIM knowledge profile (`ecosim-2dea74d9`) was built from | match (exit 0) |

Drift is expected and is not a reason to stop: the model is onboarded, and A2MC reasons with the
registered profile, which describes `2dea74d9` rather than your commit. Record which commit you
built in the case's research plan.

## What you need

- `git`, `cmake`, and a C, C++ and Fortran compiler from **GCC 13 or older**
- about 30 minutes; the build compiles its own HDF5, netCDF-C, netCDF-Fortran and zlib. **An agent
  runs it in the background** (or hands the user the command for their own terminal): one tool call is
  usually capped well below 30 minutes, and a killed build leaves a half-written `build/`

**GCC 14 does not work.** It fails inside the bundled netCDF-C with
`implicit declaration of function 'strcasecmp'`, because GCC 14 made that warning an error and the
bundled netCDF predates the fix. Nothing in the message points at the compiler. Check
`gcc --version` first.

## Build

```bash
git clone --recursive https://github.com/jingtao-lbl/EcoSIM.git
cd EcoSIM
git submodule update --init --recursive

# Pass all three compilers explicitly. On Perlmutter the default gcc-native/14 is on PATH, and
# the system GCC 13 lives in /usr/bin:
PATH=/usr/bin:$PATH bash build_EcoSIM.sh CC=/usr/bin/gcc CXX=/usr/bin/g++ FC=/usr/bin/gfortran
# On macOS, Homebrew's gcc@13 instead (not yet verified):
#   bash build_EcoSIM.sh CC=$(brew --prefix gcc@13)/bin/gcc-13 CXX=.../g++-13 FC=.../gfortran-13
```

**`build_EcoSIM.sh` exits 0 even when the build fails.** The only reliable test is the binary:

```bash
ls -la build/*/bin/ecosim.f90.x        # about 25 MB; on Perlmutter build/Linux-x86_64-double-Release/
```

If you switch compilers after a failed attempt, delete `build/` first: its CMake cache remembers
the compiler that failed. In an agent harness, load modules in the **same** command as the build,
because each shell call starts fresh.

The binary is serial (built with `mpi=0`), so an EcoSIM ensemble runs one process per case, on a
scheduler or, with `A2MC_EXEC_MODE=local`, on a workstation.

## Archive it, then bind to the archive

EcoSIM builds into one shared tree, so the next build overwrites this binary in place, and a queued
job resolves its executable when it starts. Archive right after the build, while the tree still
matches it:

```bash
tools/model_archive_build.sh --tree /path/to/EcoSIM \
    --binary build/Linux-x86_64-double-Release/bin/ecosim.f90.x --archive /path/to/EcoSIM/build_archive
```

Then point the case's `A2MC_ECOSIM_BINARY` at the archived copy, never at `build/`.

## Verify

```bash
python tools/model_preflight.py --model ecosim --checkout /path/to/EcoSIM
```

Exit 0 (match) or 3 (drift) means the checkout is usable; the verdict says which.
