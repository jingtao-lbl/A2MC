# Adapter Conformance Validator — ats

**Adapter path:** `models/ats`
**Timestamp:** 2026-07-28T02:38:59+00:00
**Overall verdict:** **Yellow**

## Dimension summary

| Dim | Name | Pass | Total | Ratio | Verdict |
|-----|------|------|-------|-------|---------|
| 1 | Required files present | 9 | 11 | 82% | WARN |
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

## Dimension 1: Required files present — WARN

### Failures

- **FAIL:** missing required file: curated_seed.yaml (models/ats/curated_seed.yaml)
- **FAIL:** missing runtemplates/ directory (models/ats/runtemplates)

### Passes (9)

- __init__.py present (models/ats/__init__.py)
- spec.py present (models/ats/spec.py)
- backend.py present (models/ats/backend.py)
- datasets.py present (models/ats/datasets.py)
- prompts.py present (models/ats/prompts.py)
- version.py present (models/ats/version.py)
- parameter_parser.py present (models/ats/parameter_parser.py)
- output_parser.py present (models/ats/output_parser.py)
- README.md present (models/ats/README.md)

## Dimension 2: ModelSpec registered — PASS

### Passes (2)

- models.ats imported successfully
- registry.get_model('ats') returned backend with spec.name='ats'

## Dimension 3: ModelBackend conformance — PASS

### Passes (10)

- backend is a ModelBackend subclass (ATSBackend)
- backend.spec.name = 'ats' matches model name
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

- ATSParameterParser.parse() returned 62 record(s)

## Dimension 6: output_parser produces non-empty output — PASS

### Passes (1)

- ATSOutputParser.parse() returned 9 record(s)

## Dimension 7: Datasets registered — PASS

### Passes (1)

- 1 dataset version(s) registered: ['ats-b044298a']

## Triage discipline (per docs/a2mc_reference/rag_validation_workflow.md)

Each finding falls into one of four categories — categorize before fixing:

| Category | Action | Where the fix lives |
|---|---|---|
| Real fabrication / drift | Patch the artifact | adapter source |
| Validator false positive | Add filter pattern | this validator script |
| By-design scope mismatch | Tag with metadata | spec / dataset entry |
| Threshold mis-calibration | Adjust threshold | this validator script |

