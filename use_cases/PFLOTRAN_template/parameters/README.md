# `parameters/` — the parameter lists and the sampled design matrices

**One parameter list and one matrix per round.** The list declares what is calibrated and within what bounds; the matrix is the sample drawn from it. Column `j` of the matrix is row `j` of the list, and nothing re-derives that mapping at analysis time.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| designing a round's list and sampling it | **`phase0-design`**, then `pflotran-run-workflow` |
| refining bounds from published ranges | **`literature-review`** (its PARAMETER-BOUNDS mode) |
| checking what a parameter actually does | `phase3-diagnosis` — and the model's own source, never the name |

## The parameter surfaces, and a parameter belongs to exactly one

| surface | what it is | treatment |
|---|---|---|
| the input deck | `pflotran.in` -- cards addressed by block path | rewritten per case |
| the thermodynamic database | e.g. `savannah_river.dat` | a second tuned surface |

## The rules that bite

- **`bound_source` is required on every row**, from a five-term vocabulary: `measured:` · `literature:` · `database:` · `prior_round:` · `provisional:`. `tools/check_bound_source.py` enforces it. A naive ±50% envelope is not a bound source.
- **Case *N* is design-matrix row *N−1*.** Adjacent Saltelli rows agree in most columns, so an off-by-one returns the right value most of the time and a silently wrong one otherwise. A spot check will not reveal it.
- **Where the docs and the source disagree on a card name, the SOURCE name wins.** Two upstream doc typos were found this way.
- Some cards are **not writable** (`writable: False` in the mined registry). A parameter list that includes one produces a case that silently ignores it.
- **Bounds here are `provisional:` by construction** unless refined -- the seed was default-anchored, not literature-derived. Say so in `bound_source` rather than implying a provenance the row does not have.

## Verify before submitting

```bash
python tools/check_bound_source.py
python scripts/validate_adapter_ensemble.py --expect-baseline
```
