# EcoSIM run templates

Rendered by `scripts/init_adapter.py` (Step 11) / the ensemble generator into a
submittable job script. `{{PLACEHOLDER}}` tokens are per-case knobs; the
EcoSIM-specific parts are filled in because they are **verified**, not guessed.

| Template | Status | Notes |
|---|---|---|
| `hpc_standalone.sh.tmpl` | **PROVEN** | Serial Fortran binary on Perlmutter/Slurm. Encodes the working GCC-13 build + `ecosim.f90.x <namelist>` invocation from the BioCON test1_ex1 reproduction (`memory/dev_logs_adapterkit/20260711c`). Renders to valid bash (`bash -n` clean). |
| `local_standalone` | deferred | Same binary, no scheduler — trivial from the HPC variant when needed. |
| `hpc_cime` / `local_cime` | N/A | EcoSIM is not CIME-managed. |
| `hpc_python` / `local_python` | N/A | EcoSIM is a compiled binary, not Python. |

## Verified facts baked into `hpc_standalone`
- **Build with GCC ≤ 13**, never the default Perlmutter `gcc-native/14` (breaks the netcdf-c TPL). Binary: `EcoSIM/build/Linux-x86_64-double-Release/bin/ecosim.f90.x`.
- **Serial** (build default `mpi=0`) → `-q shared`, 1 task.
- **Run length** is set by `forc_periods = <y0>,<y1>,1` in the namelist, **not** `stop_n` (non-binding). Run the namelist as-is; no stop-config edit.
- Expected output: `<case>.ecosim.h0.<start-date>.nc` (h0 history tape, 516 vars).

The other 5 variants of the standard runtemplate matrix are intentionally not
authored yet (EcoSIM only needs the standalone HPC path for the calibration
ensemble). Add them when a use case requires them — do not ship empty
placeholders.
