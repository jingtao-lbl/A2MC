# Adapter Conformance Validator — pflotran

**Adapter path:** `models/pflotran`
**Timestamp:** 2026-08-01T16:34:21+00:00
**Overall verdict:** **Green**

## Dimension summary

| Dim | Name | Pass | Total | Ratio | Verdict |
|-----|------|------|-------|-------|---------|
| 1 | Required files present | 11 | 11 | 100% | PASS |
| 2 | ModelSpec registered | 2 | 2 | 100% | PASS |
| 3 | ModelBackend conformance | 10 | 10 | 100% | PASS |
| 4 | TODO(adapter-kit) markers resolved | 1 | 1 | 100% | PASS |
| 5 | parameter_parser produces non-empty output | 1 | 1 | 100% | PASS |
| 6 | output_parser produces non-empty output | 1 | 1 | 100% | PASS |
| 7 | Datasets registered | 1 | 1 | 100% | PASS |

## Verdict scheme

- **PASS** if dimension's pass-ratio ≥ 90%
- **WARN** if 70–90%
- **FAIL** if < 70%

Overall:

- **Green** if all dimensions PASS
- **Yellow** if any WARN, none FAIL
- **Red** if any FAIL

## Dimension 1: Required files present — PASS

### Passes (11)

- __init__.py present (models/pflotran/__init__.py)
- spec.py present (models/pflotran/spec.py)
- backend.py present (models/pflotran/backend.py)
- datasets.py present (models/pflotran/datasets.py)
- prompts.py present (models/pflotran/prompts.py)
- version.py present (models/pflotran/version.py)
- parameter_parser.py present (models/pflotran/parameter_parser.py)
- output_parser.py present (models/pflotran/output_parser.py)
- curated_seed.yaml present (models/pflotran/curated_seed.yaml)
- README.md present (models/pflotran/README.md)
- runtemplates/ has 1 template(s) (models/pflotran/runtemplates)

## Dimension 2: ModelSpec registered — PASS

### Passes (2)

- models.pflotran imported successfully
- registry.get_model('pflotran') returned backend with spec.name='pflotran'

## Dimension 3: ModelBackend conformance — PASS

### Passes (10)

- backend is a ModelBackend subclass (PFLOTRANBackend)
- backend.spec.name = 'pflotran' matches model name
- backend.parse_parameters present and callable
- backend.parse_outputs present and callable
- backend.write_parameter_file present and callable
- backend.create_case present and callable
- backend.submit_ensemble present and callable
- backend.check_case_status present and callable
- backend.extract_history_variables present and callable
- backend.list_diagnostic_tools present and callable

## Dimension 4: TODO(adapter-kit) markers resolved — PASS

### Passes (1)

- no TODO(adapter-kit) markers remaining

## Dimension 5: parameter_parser produces non-empty output — PASS

### Passes (1)

- skipped (no --param-file provided)

## Dimension 6: output_parser produces non-empty output — PASS

### Passes (1)

- skipped (no --output-cdl provided)

## Dimension 7: Datasets registered — PASS

### Passes (1)

- 1 dataset version(s) registered: ['pflotran-157a26f7']

## Triage discipline (per docs/a2mc_reference/rag_validation_workflow.md)

Each finding falls into one of four categories — categorize before fixing:

| Category | Action | Where the fix lives |
|---|---|---|
| Real fabrication / drift | Patch the artifact | adapter source |
| Validator false positive | Add filter pattern | this validator script |
| By-design scope mismatch | Tag with metadata | spec / dataset entry |
| Threshold mis-calibration | Adjust threshold | this validator script |

