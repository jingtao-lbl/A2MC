# `parameters/` — the parameter lists and the sampled design matrices

**One parameter list and one matrix per round.** The list declares what is calibrated and within what bounds; the matrix is the sample drawn from it. Column `j` of the matrix is row `j` of the list, and nothing re-derives that mapping at analysis time.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| designing a round's list and sampling it | **`phase0-design`**, then `offline-testing-workflow` |
| refining bounds from published ranges | **`literature-review`** (its PARAMETER-BOUNDS mode) |
| carrying a tuned base across model versions | **`port-param-file`** |
| checking what a parameter actually does | `phase3-diagnosis` — and the model's own source, never the name |

## The parameter surfaces, and a parameter belongs to exactly one

| surface | what it is | treatment |
|---|---|---|
| the FATES parameter file | NetCDF/CDL through api-31, **JSON from api-43** | perturbed per case |

## The rules that bite

- **`bound_source` is required on every row**, from a five-term vocabulary: `measured:` · `literature:` · `database:` · `prior_round:` · `provisional:`. `tools/check_bound_source.py` enforces it. A naive ±50% envelope is not a bound source.
- **Case *N* is design-matrix row *N−1*.** Adjacent Saltelli rows agree in most columns, so an off-by-one returns the right value most of the time and a silently wrong one otherwise. A spot check will not reveal it.
- **Official FATES parameter names carry no PFT suffix.** A2MC's Morris shorthand does (`vmax_p_10`); the two are different namespaces and `build_param_lookup()` converts. PFT specificity lives in its own field, never inside a key.
- **PFT ids are NOT stable across versions.** Map by functional type and verify against `fates_pftname` in the base file; derive the PFT count, never hardcode it.
- **A parameter's `long_name`/`units` can be wrong.** Verify in the source equations before writing a bound -- `l2fr` is fine root per leaf, which its name does not say.

## Verify before submitting

```bash
python tools/check_bound_source.py
python tools/validate_param_list.py
```
