# Getting and building PFLOTRAN

The one place A2MC records how to get PFLOTRAN's source and build a working binary. `a2mc-init` Step 2 sends a user here when there is no built PFLOTRAN on the machine; `onboard-case` Step 2 then binds a case to the archived binary. Update this file in place when the recipe changes.

> **Status, 2026-09-23: a working Perlmutter recipe exists again, on `cpe/25.09`.** The 2026-08-07 recipe pinned Cray PE release 23.12, which NERSC removed (found 2026-09-22), and with it the libraries both the shared PETSc 3.21 and the first archived binary linked. Option 2 below was taken: PETSc 3.21.4 was rebuilt against `cpe/25.09`, and PFLOTRAN at `157a26f7` against that. The build, the archive and a login-node smoke test pass; and the reproducibility check against the old binary and the team's reference **passes** on both decks it was run on (the last section of the recipe).

## Source and pin

- Source: `https://bitbucket.org/pflotran/pflotran` (a Bitbucket repository; there is no current GitHub mirror).
- Pin: commit `157a26f7`, the commit A2MC's PFLOTRAN knowledge profile (`pflotran-157a26f7`) was built from. `model_preflight` reports any other commit as **DRIFT** (exit 3).
- The pin needs **PETSc 3.21.x**: `pflotran_constants.F90` refuses anything older than 3.21.4, and PETSc 3.23 and newer require `use petscsys`, which this commit predates. A test against PETSc 3.24 failed with 279 errors from that single cause.

## If the toolchain disappears again

Cray PE releases are removed on NERSC's schedule, not ours, and a removal breaks every binary linked against them. The options, cheapest first:

1. Ask the PFLOTRAN developers, who maintain the PETSc builds in NERSC's shared PFLOTRAN tree (`/global/common/software/pflotran`), whether a PETSc 3.21.4 exists for a current Cray PE.
2. Rebuild PETSc 3.21.4 against a current Cray PE, then PFLOTRAN at `157a26f7` against it. This is what the recipe below does, and it took under ten minutes of build time.
3. Move the pin to a PFLOTRAN commit that supports PETSc 3.24.3 or newer. That is a new model version, so it also needs a new knowledge profile (the `rebuild-rag` skill) and a reproducibility check against the old pin's reference output.

## The recipe (2026-09-23, `cpe/25.09`)

### 1. A source tree of your own at the pin

Build in a clone you control, checked out at `157a26f7`. If the only PFLOTRAN checkout on the machine is on someone else's branch, clone it rather than switching it: another lane may be building or running from it.

```bash
git clone https://bitbucket.org/pflotran/pflotran <build dir>/PFLOTRAN_anchor_157a26f7
cd <build dir>/PFLOTRAN_anchor_157a26f7
git checkout -b a2mc-anchor-157a26f7 157a26f73e4c939a22ffe6eb60155fb9a3d36ff9
git remote set-url --push origin DISABLED          # never push model source upstream
```

Use a **clone, not a `git worktree`**: `tools/model_archive_build.sh` requires a `.git` directory, and a worktree has a `.git` file.

### 2. One environment script, sourced for the build and for every run

```bash
module load cpu                          # CPU stack: drops cudatoolkit and craype-accel-nvidia80
module unload darshan                    # a default module that injects itself into the link
module load cpe/25.09                    # PrgEnv-gnu 8.6.0, cray-mpich 9.0.1, cray-libsci 25.09.0
module load gcc-native/14                # gfortran 14.3.0, pinned explicitly
module load cray-hdf5-parallel/1.14.3.7  # the 25.09 default
export PETSC_DIR=<software dir>/petsc-3.21.4
export PETSC_ARCH=arch-perlmutter-gnu-opt-cpe2509
```

On Perlmutter the maintained copy of exactly this file is `~/pflotran_env_157a26f7_cpe2509.sh`. Two traps, both silent:

- `module load PrgEnv-gnu` **after** `cpe/25.09` reverts every version it pinned. `cpe/25.09` loads the right PrgEnv itself.
- `module purge` breaks `MODULEPATH` on Perlmutter.

Put PETSc under `/global/common/software/<project>` on NERSC if you can: that filesystem is built for shared libraries that many jobs load at once.

### 3. PETSc 3.21.4

The configure options are those of the shared build it replaces, with only the HDF5 directory changed. Its three downloaded packages resolve to the same commits as that build did (hypre `ee74c20e`, metis `69fb26dd`, parmetis `f5e3aab0`), so the toolchain is the only difference.

```bash
cd <software dir>
curl -sSfL -O https://web.cels.anl.gov/projects/petsc/download/release-snapshots/petsc-3.21.4.tar.gz
tar xzf petsc-3.21.4.tar.gz && cd petsc-3.21.4
export TMPDIR=<a scratch dir you own>              # keep configure's temp files off the node's /tmp
./configure --COPTFLAGS='-g -O3' --CXXOPTFLAGS='-g -O3' \
  --FOPTFLAGS='-g -O3 -fallow-argument-mismatch' \
  --download-hypre --download-metis --download-parmetis \
  --with-batch=0 --with-cc=cc --with-cxx=CC --with-fc=ftn --with-cuda=0 --with-debugging=0 \
  --with-hdf5-dir=/opt/cray/pe/hdf5-parallel/1.14.3.7/gnu/12.3 \
  --with-make-np=8 --with-mpiexec=srun PETSC_ARCH=$PETSC_ARCH
make PETSC_DIR=$PETSC_DIR PETSC_ARCH=$PETSC_ARCH all
```

Cray ships HDF5 1.14.3.7 built for gnu 12.3 only, and gfortran 14.3 read its Fortran module files without complaint. The rule that still holds is the narrower one: build PETSc and PFLOTRAN with the same compiler.

`make check` is skipped on a login node because it launches through `srun`. The PFLOTRAN smoke test and the reproducibility runs below test the library.

### 4. PFLOTRAN

```bash
cd <build dir>/PFLOTRAN_anchor_157a26f7/src/pflotran && make -j 16 pflotran   # make, not CMake
```

About 310 compile lines, warnings only. The Cray wrappers embed RPATHs, so the binary finds cray-mpich 9.0.1, libsci 25.09 and HDF5 1.14.3.7 even from a shell with the login default (`cpe/26.03`) loaded. Load the build modules at run time anyway: they also set the MPI runtime environment.

### 5. Archive it at once, then bind to the archive

PFLOTRAN builds into one shared tree, so the next build overwrites the binary in place, and a queued job resolves its executable when it starts. Archive before building anything else:

```bash
tools/model_archive_build.sh --tree <build dir>/PFLOTRAN_anchor_157a26f7 \
    --binary src/pflotran/pflotran --archive <archive root> \
    --label anchor_cpe2509 --commit 157a26f7
```

Then add a `SHA256:` line (and `Source`, `Change`, `Binary`, `Toolchain`) to the archive's `PROVENANCE.txt`, because `tools/binary_archive_manifest.py` checks the binary against that line and the archive script does not write it. Record the archive with `tools/binary_archive_manifest.py --generate --model pflotran` and confirm with `--verify --model pflotran`.

On Perlmutter the archive is `~/PFLOTRAN/build_archive/anchor_cpe2509_157a26f7/pflotran` (SHA256 `c9510c94…`). A case binds to it through `A2MC_PFLOTRAN_BINARY` and loads the modules through `A2MC_PFLOTRAN_MODULES`, both in its site config.

### 6. Verify

| check | expect |
|---|---|
| `ldd <archived binary> \| grep 'not found'` | nothing |
| `<archived binary> -pflotranin does_not_exist.in` on a login node, environment sourced | exit **87** and `ERROR: File: "does_not_exist.in" not found.` (MPI and PETSc initialised) |
| the reproducibility runs below | the scored targets do not move (they did not: largest ratio change 1e-04) |

### The reproducibility check for this rebuild

A rebuild on a new compiler, MPI and HDF5 cannot be bit-for-bit identical to the old binary, so the criterion is the one the first build's gate used (PFLOTRAN_miniLEO's `20260807c` V0 log): divergence that is bounded, does not grow through the run, and does not move the scored targets. Two runs of the new archived binary, each scored through A2MC's own reducer with the case's current `targets.yaml`:

| run | deck | ranks | compared with |
|---|---|---|---|
| team deck | the team's unmodified miniLEO deck | 1 | the team's reference tape, and the old binary's tape of the same deck (the 2026-08-07 V0 run) |
| round base | PFLOTRAN_miniLEO R1's round base (its V0 case) | 8 | the old binary's `miniLEO_case0` tape from the R1 ensemble |

**Results (2026-09-23): passes on both decks.** Every tape is scored with the case's current `targets.yaml` (eleven targets); "largest ratio change" is the largest change in any target's simulated/observed ratio, and "worst gap" the largest relative difference at any single timestep in the scored window (model hours 806 to 1574), over the ten scored solutes.

| comparison | total score | largest ratio change | worst gap in the window |
|---|---|---|---|
| team deck: **old binary vs team reference** (control) | 0.354035 vs 0.354036 | 1.4e-04 | 4.40% |
| team deck: **new binary vs team reference** | 0.354034 vs 0.354036 | 9.9e-05 | 4.40% |
| team deck: new binary vs old binary | 0.354034 vs 0.354035 | 4.2e-05 | 2.9% |
| round base (8 ranks): new binary vs old binary | 0.354023 vs 0.354025 | 4.6e-05 | 4.2% |

The control reproduces the first build's own gate (worst gap 4.40% in the window, 17% in the transient before it), so the comparison measures what it should. The new binary is at least as close to the team's reference as the old one was, and the two binaries are closer to each other than either is to the reference. In every pair the divergence peaks before the scored window and falls to well under 0.1% by the end of the run: it does not grow. Run time: the team deck took 65.4 minutes serially (the old binary 60.3), the round base 15.6 minutes on 8 ranks (the old binary 22.4).

## The 2026-08-07 recipe, for the record

The first build linked the PETSc 3.21.4 in NERSC's shared PFLOTRAN tree (`/global/common/software/pflotran/petsc-3.21`), built with gfortran 12.3.0, cray-mpich 8.1.28, cray-hdf5-parallel 1.12.2.9 and cray-libsci 23.12.5, which shipped together as `cpe/23.12`. That release is gone, so neither that PETSc nor the binary archived from it (`R1_anchor_157a26f7`) runs on Perlmutter any more. The archive is kept: it is the binary PFLOTRAN_miniLEO's R1 ensemble ran, and its checksum is the provenance of those results.

## On a workstation

There is no local (no-scheduler) execution path for PFLOTRAN yet. Without `sbatch` the backend does not run the cases, so use a machine with a scheduler.
