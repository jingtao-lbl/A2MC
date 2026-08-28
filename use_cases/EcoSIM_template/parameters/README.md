# `parameters/` — the parameter lists and the sampled design matrices

**One parameter list and one matrix per round.** The list declares what is calibrated and within what bounds; the matrix is the sample drawn from it. Column `j` of the matrix is row `j` of the list, and nothing re-derives that mapping at analysis time.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| designing a round's list and sampling it | **`phase0-design`**, then `ecosim-run-workflow` |
| refining bounds from published ranges | **`literature-review`** (its PARAMETER-BOUNDS mode) |
| checking what a parameter actually does | `phase3-diagnosis` — and the model's own source, never the name |

## The parameter surfaces, and a parameter belongs to exactly one

| surface | what it is | treatment |
|---|---|---|
| primary | plant traits (NetCDF) | perturbed per case |
| secondary | management (NetCDF, `pft_mgmt_in`) | **staged FIXED, never edited** -- planting density lives here as a **text token**, not a numeric variable |
| tertiary | microbial kinetics (`MicrobePars…nc`) | perturbed per case |

## The rules that bite

- **`bound_source` is required on every row**, from a five-term vocabulary: `measured:` · `literature:` · `database:` · `prior_round:` · `provisional:`. `tools/check_bound_source.py` enforces it. A naive ±50% envelope is not a bound source.
- **Case *N* is design-matrix row *N−1*.** Adjacent Saltelli rows agree in most columns, so an off-by-one returns the right value most of the time and a silently wrong one otherwise. A spot check will not reveal it.
- **Routing is DERIVED, never declared.** `route_surfaces()` probes each base file's variable names and raises if a parameter is found in both or neither. The optional `surface` column is cross-checked against that probe -- documentation, not a second source of truth. A validator that reads only the primary surface passes while the microbial parameters are silently unwritten.
- **The `pft` column is overloaded.** For microbial parameters it indexes a non-PFT axis whose slots are kinetic/recalcitrant. Declare the real axis as its own column.

## Verify before submitting

```bash
python tools/check_bound_source.py
python scripts/validate_adapter_ensemble.py --expect-baseline
```
