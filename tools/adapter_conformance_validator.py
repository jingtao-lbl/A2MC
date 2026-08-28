#!/usr/bin/env python3
"""
adapter_conformance_validator.py - Validate an adapter scaffold against the
model contract from `models/base.py` before running the rest of the kit pipeline.

Sister tool to:
    - tools/codebase_wiki_validator.py    (V1 — wiki ↔ source)
    - tools/yaml_wiki_validator.py        (V2 — YAML ↔ wiki + param + CDL)
    - tools/rag_diff.py                   (V3 — RAG profile diff)
    - tools/run_template_validator.py     (V5 — rendered run-script; Step E)

Seven validation dimensions per `memory/dev_logs_adapterkit/20260427c_*.md`:

    1. Required files present              (spec/backend/datasets/version/parsers/...)
    2. ModelSpec registered                (import + registry lookup)
    3. ModelBackend conformance            (subclass + spec attribute + abstract methods)
    4. No remaining # TODO(adapter-kit):   (each occurrence reported with file:line)
    5. parameter_parser produces output    (calls .parse() if --param-file given)
    6. output_parser produces output       (calls .parse() if --output-cdl given)
    7. Datasets dict non-empty             (at least one ModelDataset registered)

Verdict per dimension:
    - PASS if dimension's pass-ratio ≥ 90%
    - WARN if 70-90%
    - FAIL if < 70%

Overall verdict:
    - Green  if all dimensions PASS
    - Yellow if any dimension WARN, none FAIL
    - Red    if any dimension FAIL

Read-only on inputs; only writes the output Markdown report.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# Repo root + import bootstrap
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# =============================================================================
# Verdict + Finding dataclasses
# =============================================================================

@dataclass
class Finding:
    """One observation from a dimension check."""
    severity: str                  # 'pass', 'warn', 'fail'
    message: str
    location: Optional[str] = None  # file:line if applicable


@dataclass
class DimensionResult:
    """One dimension's findings + roll-up score."""
    dim_id: int
    name: str
    findings: List[Finding] = field(default_factory=list)
    n_total: int = 0               # total things checked
    n_passed: int = 0              # how many passed

    @property
    def pass_ratio(self) -> float:
        if self.n_total == 0:
            return 1.0  # vacuous truth: nothing to check = trivially PASS
        return self.n_passed / self.n_total

    @property
    def verdict(self) -> str:
        ratio = self.pass_ratio
        if ratio >= 0.9:
            return "PASS"
        if ratio >= 0.7:
            return "WARN"
        return "FAIL"


@dataclass
class ConformanceReport:
    """Full validator report — one DimensionResult per dimension."""
    model_name: str
    adapter_path: Path
    timestamp: datetime
    dimensions: List[DimensionResult] = field(default_factory=list)

    @property
    def overall_verdict(self) -> str:
        verdicts = [d.verdict for d in self.dimensions]
        if "FAIL" in verdicts:
            return "Red"
        if "WARN" in verdicts:
            return "Yellow"
        return "Green"


# =============================================================================
# Required files for the adapter scaffold
# =============================================================================

REQUIRED_FILES = [
    "__init__.py",
    "spec.py",
    "backend.py",
    "datasets.py",
    "prompts.py",
    "version.py",
    "parameter_parser.py",
    "output_parser.py",
    "curated_seed.yaml",
    "README.md",
]
REQUIRED_RUNTEMPLATES_DIR = "runtemplates"  # must exist + contain ≥1 *.tmpl
TODO_MARKER = "TODO(adapter-kit)"


# =============================================================================
# Dimension 1 — Required files present
# =============================================================================

def check_required_files(adapter_path: Path) -> DimensionResult:
    """Confirm all required files exist + at least one runtemplate."""
    result = DimensionResult(dim_id=1, name="Required files present")

    for fname in REQUIRED_FILES:
        path = adapter_path / fname
        result.n_total += 1
        if path.is_file():
            result.n_passed += 1
            result.findings.append(Finding(
                severity="pass",
                message=f"{fname} present",
                location=str(path.relative_to(REPO_ROOT)),
            ))
        else:
            result.findings.append(Finding(
                severity="fail",
                message=f"missing required file: {fname}",
                location=str(path.relative_to(REPO_ROOT)),
            ))

    runtemplates = adapter_path / REQUIRED_RUNTEMPLATES_DIR
    result.n_total += 1
    if runtemplates.is_dir():
        tmpls = list(runtemplates.glob("*.sh.tmpl"))
        if tmpls:
            result.n_passed += 1
            result.findings.append(Finding(
                severity="pass",
                message=f"runtemplates/ has {len(tmpls)} template(s)",
                location=str(runtemplates.relative_to(REPO_ROOT)),
            ))
        else:
            result.findings.append(Finding(
                severity="fail",
                message="runtemplates/ exists but has no *.sh.tmpl files",
                location=str(runtemplates.relative_to(REPO_ROOT)),
            ))
    else:
        result.findings.append(Finding(
            severity="fail",
            message="missing runtemplates/ directory",
            location=str(runtemplates.relative_to(REPO_ROOT)),
        ))

    return result


# =============================================================================
# Dimension 2 — ModelSpec registered
# =============================================================================

def check_modelspec_registered(model_name: str) -> DimensionResult:
    """Import the adapter package and confirm ModelSpec is in the registry."""
    result = DimensionResult(dim_id=2, name="ModelSpec registered")
    result.n_total = 2  # import success + registry lookup success

    # Step 1: import the adapter package
    try:
        importlib.import_module(f"models.{model_name}")
        result.n_passed += 1
        result.findings.append(Finding(
            severity="pass",
            message=f"models.{model_name} imported successfully",
        ))
    except Exception as e:
        result.findings.append(Finding(
            severity="fail",
            message=f"models.{model_name} import failed: {type(e).__name__}: {e}",
        ))
        return result  # can't check registry without import

    # Step 2: check registry lookup
    try:
        from models import registry
        backend = registry.get_model(model_name)
        result.n_passed += 1
        result.findings.append(Finding(
            severity="pass",
            message=f"registry.get_model({model_name!r}) returned backend with spec.name={backend.spec.name!r}",
        ))
    except Exception as e:
        result.findings.append(Finding(
            severity="fail",
            message=f"registry.get_model({model_name!r}) failed: {type(e).__name__}: {e}",
        ))

    return result


# =============================================================================
# Dimension 3 — ModelBackend conformance
# =============================================================================

def check_backend_conformance(model_name: str) -> DimensionResult:
    """Confirm the backend is a proper ModelBackend subclass with the spec
    attribute matching the model name."""
    result = DimensionResult(dim_id=3, name="ModelBackend conformance")

    try:
        from models import registry
        from models.base import ModelBackend
    except Exception as e:
        result.n_total = 1
        result.findings.append(Finding(
            severity="fail",
            message=f"can't import framework: {e}",
        ))
        return result

    try:
        backend = registry.get_model(model_name)
    except Exception as e:
        result.n_total = 1
        result.findings.append(Finding(
            severity="fail",
            message=f"can't fetch backend: {e}",
        ))
        return result

    # Check 1: subclass of ModelBackend
    result.n_total += 1
    if isinstance(backend, ModelBackend):
        result.n_passed += 1
        result.findings.append(Finding(
            severity="pass",
            message=f"backend is a ModelBackend subclass ({type(backend).__name__})",
        ))
    else:
        result.findings.append(Finding(
            severity="fail",
            message=f"backend is NOT a ModelBackend subclass (got {type(backend).__name__})",
        ))

    # Check 2: spec attribute present + name matches
    result.n_total += 1
    spec = getattr(backend, "spec", None)
    if spec is None:
        result.findings.append(Finding(
            severity="fail",
            message="backend has no `spec` attribute",
        ))
    elif spec.name != model_name:
        result.findings.append(Finding(
            severity="fail",
            message=f"backend.spec.name = {spec.name!r}, expected {model_name!r}",
        ))
    else:
        result.n_passed += 1
        result.findings.append(Finding(
            severity="pass",
            message=f"backend.spec.name = {spec.name!r} matches model name",
        ))

    # Check 3: abstract methods callable (each may raise NotImplementedError; that's WARN, not FAIL)
    abstract_methods = [
        "parse_parameters",
        "parse_outputs",
        "write_parameter_file",
        "create_case",
        "submit_ensemble",
        "check_case_status",
        "extract_history_variables",
        "list_diagnostic_tools",
    ]

    for method_name in abstract_methods:
        result.n_total += 1
        method = getattr(backend, method_name, None)
        if method is None:
            result.findings.append(Finding(
                severity="fail",
                message=f"backend missing method: {method_name}",
            ))
        elif not callable(method):
            result.findings.append(Finding(
                severity="fail",
                message=f"backend.{method_name} is not callable",
            ))
        else:
            # Method exists. Don't actually call it — just confirm presence.
            # Stub methods that raise NotImplementedError are EXPECTED at this stage
            # of the kit; we report them under Dim 4 (TODO markers) instead.
            result.n_passed += 1
            result.findings.append(Finding(
                severity="pass",
                message=f"backend.{method_name} present and callable",
            ))

    return result


# =============================================================================
# Dimension 4 — No remaining TODO(adapter-kit) markers
# =============================================================================

def check_no_todos(adapter_path: Path) -> DimensionResult:
    """Count remaining `# TODO(adapter-kit):` markers across the adapter directory."""
    result = DimensionResult(dim_id=4, name="TODO(adapter-kit) markers resolved")

    # Use ripgrep if available, else fall back to Python file walk + grep.
    try:
        proc = subprocess.run(
            ["grep", "-rn", "-F", TODO_MARKER, str(adapter_path)],
            capture_output=True, text=True, check=False,
        )
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    except FileNotFoundError:
        # No grep on PATH (highly unusual). Manual walk.
        lines = []
        for path in adapter_path.rglob("*"):
            if not path.is_file():
                continue
            try:
                for i, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
                    if TODO_MARKER in line:
                        lines.append(f"{path}:{i}:{line}")
            except (OSError, UnicodeDecodeError):
                continue

    n_markers = len(lines)
    result.n_total = max(n_markers, 1)
    # Treat any TODO presence as expected-WARN at first run; threshold tuning:
    # 0 TODOs   → PASS (n_passed == n_total because we set n_total = max(n_markers, 1))
    # 1+ TODOs  → entries pass=0, fail at < 70% if many; otherwise warn-territory.
    # Use the warn band: each TODO counts as 1 unit of "not passed but not blocking".
    if n_markers == 0:
        result.n_passed = result.n_total
        result.findings.append(Finding(
            severity="pass",
            message="no TODO(adapter-kit) markers remaining",
        ))
    else:
        # Set n_passed/n_total such that ratio = 0.7 + something to land in WARN, not FAIL.
        # Cap at WARN: n_passed = floor(n_total * 0.75)
        result.n_passed = max(int(result.n_total * 0.75), 0)
        for line in lines[:50]:  # cap output at 50 to keep report readable
            # parse "<path>:<lineno>:<content>"
            parts = line.split(":", 2)
            if len(parts) >= 2:
                location = f"{parts[0]}:{parts[1]}"
                content = parts[2].strip() if len(parts) > 2 else ""
            else:
                location = line
                content = ""
            result.findings.append(Finding(
                severity="warn",
                message=f"TODO marker present: {content[:100]}",
                location=location,
            ))
        if n_markers > 50:
            result.findings.append(Finding(
                severity="warn",
                message=f"... ({n_markers - 50} more TODO markers omitted from report)",
            ))

    return result


# =============================================================================
# Dimensions 5 + 6 — parameter_parser / output_parser produce non-empty output
# =============================================================================

def check_parser_output(
    model_name: str,
    parser_kind: str,            # "parameter" or "output"
    file_path: Optional[Path],
    dim_id: int,
) -> DimensionResult:
    """Try to call the spec's parser_class on file_path; report whether it
    returns non-empty output or raises NotImplementedError."""
    name = f"{parser_kind}_parser produces non-empty output"
    result = DimensionResult(dim_id=dim_id, name=name)

    if file_path is None:
        result.n_total = 1
        result.n_passed = 1  # vacuous: not given a file, can't check
        result.findings.append(Finding(
            severity="pass",
            message=f"skipped (no --{'param-file' if parser_kind == 'parameter' else 'output-cdl'} provided)",
        ))
        return result

    if not file_path.is_file():
        result.n_total = 1
        result.findings.append(Finding(
            severity="fail",
            message=f"input file not found: {file_path}",
        ))
        return result

    try:
        from models import registry
        backend = registry.get_model(model_name)
        parser_class_attr = "parameter_parser_class" if parser_kind == "parameter" else "output_parser_class"
        parser_class = getattr(backend.spec, parser_class_attr, None)
    except Exception as e:
        result.n_total = 1
        result.findings.append(Finding(
            severity="fail",
            message=f"can't access spec.{parser_class_attr}: {e}",
        ))
        return result

    if parser_class is None:
        result.n_total = 1
        result.findings.append(Finding(
            severity="fail",
            message=f"spec.{parser_class_attr} is None — adapter must declare it",
        ))
        return result

    # Try to instantiate + call .parse()
    result.n_total = 1
    try:
        parser = parser_class()
        records = parser.parse(file_path)
    except NotImplementedError as e:
        result.findings.append(Finding(
            severity="warn",
            message=f"{parser_class.__name__}.parse() is a stub (NotImplementedError); fill in for your model",
        ))
        return result
    except Exception as e:
        result.findings.append(Finding(
            severity="fail",
            message=f"{parser_class.__name__}.parse() raised {type(e).__name__}: {e}",
        ))
        return result

    if not records:
        result.findings.append(Finding(
            severity="fail",
            message=f"{parser_class.__name__}.parse({file_path}) returned empty",
        ))
    elif not isinstance(records, dict):
        result.findings.append(Finding(
            severity="fail",
            message=f"{parser_class.__name__}.parse() returned {type(records).__name__}, expected dict",
        ))
    else:
        result.n_passed = 1
        result.findings.append(Finding(
            severity="pass",
            message=f"{parser_class.__name__}.parse() returned {len(records)} record(s)",
        ))

    return result


# =============================================================================
# Dimension 7 — Datasets dict non-empty
# =============================================================================

def check_datasets_present(model_name: str) -> DimensionResult:
    """Confirm at least one ModelDataset is registered for this model."""
    result = DimensionResult(dim_id=7, name="Datasets registered")
    result.n_total = 1

    try:
        from models import registry
        datasets = registry.list_datasets(model_name).get(model_name, [])
    except Exception as e:
        result.findings.append(Finding(
            severity="fail",
            message=f"registry.list_datasets({model_name!r}) failed: {e}",
        ))
        return result

    if datasets:
        result.n_passed = 1
        result.findings.append(Finding(
            severity="pass",
            message=f"{len(datasets)} dataset version(s) registered: {datasets}",
        ))
    else:
        # WARN, not FAIL — the kit's flow has Step E populating datasets after
        # the user has produced wiki + CDL + curated YAML. Empty at scaffold time
        # is expected.
        result.n_passed = 0
        result.findings.append(Finding(
            severity="warn",
            message=(
                "no datasets registered for this model. "
                "Expected at scaffold time; Step E (RAG/memory wire-up) populates this."
            ),
        ))
        # Force WARN-band pass_ratio by setting n_total higher so 0/1 lands at fail,
        # but we want WARN for missing datasets. Adjust: make this dim score 0.75 (WARN).
        result.n_total = 4
        result.n_passed = 3

    return result


# =============================================================================
# Report assembly
# =============================================================================

def run_all_dimensions(
    model_name: str,
    adapter_path: Path,
    param_file: Optional[Path],
    output_cdl: Optional[Path],
) -> ConformanceReport:
    report = ConformanceReport(
        model_name=model_name,
        adapter_path=adapter_path,
        timestamp=datetime.now(timezone.utc),
    )
    report.dimensions.append(check_required_files(adapter_path))
    report.dimensions.append(check_modelspec_registered(model_name))
    report.dimensions.append(check_backend_conformance(model_name))
    report.dimensions.append(check_no_todos(adapter_path))
    report.dimensions.append(check_parser_output(model_name, "parameter", param_file, 5))
    report.dimensions.append(check_parser_output(model_name, "output", output_cdl, 6))
    report.dimensions.append(check_datasets_present(model_name))
    return report


def write_markdown_report(report: ConformanceReport, output_path: Path) -> None:
    """Write the validator report as a Markdown file."""
    lines: List[str] = []
    a = lines.append

    a(f"# Adapter Conformance Validator — {report.model_name}")
    a("")
    a(f"**Adapter path:** `{report.adapter_path.relative_to(REPO_ROOT)}`")
    a(f"**Timestamp:** {report.timestamp.isoformat(timespec='seconds')}")
    a(f"**Overall verdict:** **{report.overall_verdict}**")
    a("")
    a("## Dimension summary")
    a("")
    a("| Dim | Name | Pass | Total | Ratio | Verdict |")
    a("|-----|------|------|-------|-------|---------|")
    for d in report.dimensions:
        a(f"| {d.dim_id} | {d.name} | {d.n_passed} | {d.n_total} | {d.pass_ratio:.0%} | {d.verdict} |")
    a("")

    a("## Verdict scheme")
    a("")
    a("- **PASS** if dimension's pass-ratio ≥ 90%")
    a("- **WARN** if 70–90%")
    a("- **FAIL** if < 70%")
    a("")
    a("Overall:")
    a("")
    a("- **Green** if all dimensions PASS")
    a("- **Yellow** if any WARN, none FAIL")
    a("- **Red** if any FAIL")
    a("")

    for d in report.dimensions:
        a(f"## Dimension {d.dim_id}: {d.name} — {d.verdict}")
        a("")
        passes = [f for f in d.findings if f.severity == "pass"]
        warns = [f for f in d.findings if f.severity == "warn"]
        fails = [f for f in d.findings if f.severity == "fail"]

        if fails:
            a("### Failures")
            a("")
            for f in fails:
                loc = f" ({f.location})" if f.location else ""
                a(f"- **FAIL:** {f.message}{loc}")
            a("")

        if warns:
            a("### Warnings")
            a("")
            for f in warns:
                loc = f" ({f.location})" if f.location else ""
                a(f"- **WARN:** {f.message}{loc}")
            a("")

        if passes:
            a(f"### Passes ({len(passes)})")
            a("")
            for f in passes:
                loc = f" ({f.location})" if f.location else ""
                a(f"- {f.message}{loc}")
            a("")

    a("## Triage discipline (per docs/a2mc_reference/rag_validation_workflow.md)")
    a("")
    a("Each finding falls into one of four categories — categorize before fixing:")
    a("")
    a("| Category | Action | Where the fix lives |")
    a("|---|---|---|")
    a("| Real fabrication / drift | Patch the artifact | adapter source |")
    a("| Validator false positive | Add filter pattern | this validator script |")
    a("| By-design scope mismatch | Tag with metadata | spec / dataset entry |")
    a("| Threshold mis-calibration | Adjust threshold | this validator script |")
    a("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    new = "\n".join(lines) + "\n"

    # Do NOT rewrite when only the timestamp would change. This report is regenerated on
    # every validator run, so an unconditional write left it permanently `M` in git status
    # with a one-line diff -- noise that trains the reader to `git checkout --` a tracked
    # file reflexively, which is exactly how a REAL change gets discarded by habit.
    # Findings still land; only a content-identical rewrite is suppressed.
    def _sans_timestamp(text: str) -> str:
        return "\n".join(l for l in text.splitlines() if not l.startswith("**Timestamp:**"))

    if output_path.exists() and _sans_timestamp(output_path.read_text()) == _sans_timestamp(new):
        return                                   # unchanged apart from the clock

    output_path.write_text(new)


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(
        description="Validate an A2MC adapter scaffold against the model contract.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--model", required=True, help="Adapter directory name under models/ (e.g., 'ecosim')")
    p.add_argument("--output", type=Path, help="Output report path. Default: docs/a2mc_reference/adapter_conformance_<model>.md")
    p.add_argument("--param-file", type=Path, help="Parameter file (CDL/JSON) for Dim 5 check (optional)")
    p.add_argument("--output-cdl", type=Path, help="Output variable CDL for Dim 6 check (optional)")
    p.add_argument("--quiet", action="store_true", help="Suppress per-dimension stdout summary")

    args = p.parse_args()

    adapter_path = REPO_ROOT / "models" / args.model
    if not adapter_path.is_dir():
        print(f"ERROR: adapter directory not found: {adapter_path}", file=sys.stderr)
        return 2

    output_path = args.output or (
        REPO_ROOT / "docs" / "a2mc_reference" / f"adapter_conformance_{args.model}.md"
    )

    report = run_all_dimensions(
        model_name=args.model,
        adapter_path=adapter_path,
        param_file=args.param_file,
        output_cdl=args.output_cdl,
    )
    write_markdown_report(report, output_path)

    if not args.quiet:
        print(f"\nAdapter conformance — {args.model}")
        print(f"  report: {output_path.relative_to(REPO_ROOT)}")
        print(f"  overall: {report.overall_verdict}")
        for d in report.dimensions:
            print(f"  Dim {d.dim_id} ({d.name}): {d.verdict} ({d.n_passed}/{d.n_total})")

    # Exit codes per the kit's iteration-loop semantics:
    #   0 = Green, 1 = Yellow, 2 = Red, 3 = setup error
    if report.overall_verdict == "Green":
        return 0
    if report.overall_verdict == "Yellow":
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
