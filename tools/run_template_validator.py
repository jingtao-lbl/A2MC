#!/usr/bin/env python3
"""
run_template_validator.py - V5 of the A2MC adapter-kit validator suite.

Validate a model adapter's HPC run template(s) under
`models/<model>/runtemplates/*.tmpl` BEFORE they are used to render + submit an
ensemble. This is the run-script analog of the parse/source-scan validators:

    - tools/codebase_wiki_validator.py       (V1 — wiki ↔ source)
    - tools/yaml_wiki_validator.py           (V2 — YAML ↔ wiki + param + CDL)
    - tools/rag_diff.py                       (V3 — RAG profile diff)
    - tools/adapter_conformance_validator.py  (V4 — adapter scaffold ↔ contract)
    - tools/run_template_validator.py         (V5 — rendered run-script)  <-- THIS

Model-generic by construction: it takes `--model <name>`, loads the model's
`ModelSpec` from `models/<name>/spec.py` via `models.registry`, and dispatches
through the spec (template location, display name). It works for `--model ecosim`
now and structurally for `--model fates` later — no model-specific logic lives
here.

Per-template checks
-------------------
  1. RENDER      Enumerate every `{{PLACEHOLDER}}` token; each must be known
                 (present in the dummy-value registry) or it is flagged.
  2. SYNTAX      Substitute placeholders with safe dummy values, then run
                 `bash -n` on the rendered script (syntax check, no execution).
  3. DIRECTIVES  For a Slurm template (contains `#SBATCH`), require the core
                 directives: --account, --time, --nodes, --output.
  4. BINARY NOTE If a MODEL_BINARY placeholder exists, note that it must point at
                 an executable file at run time (informational).

Per-template verdict
--------------------
  FAIL  if `bash -n` fails, OR a required Slurm directive is missing.
  WARN  if an unknown placeholder is present (rendered with a generic dummy).
  PASS  otherwise.

Exit codes (kit iteration-loop semantics):
  0 = all templates PASS
  1 = at least one WARN, no FAIL
  2 = at least one FAIL
  3 = setup error (model/dir not found, no templates, bash unavailable)

Read-only on inputs. Renders into a temp file that is deleted after `bash -n`.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# =============================================================================
# Repo root + import bootstrap
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# =============================================================================
# Placeholder token grammar + dummy-value registry
# =============================================================================

# Placeholder tokens are `{{NAME}}` with an all-caps / digits / underscore name.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")

# Required Slurm directives for an HPC template. Matched as `#SBATCH --<name>`.
REQUIRED_SBATCH_DIRECTIVES = ("account", "time", "nodes", "output")

# Placeholder that (if present) names the model executable.
MODEL_BINARY_PLACEHOLDER = "MODEL_BINARY"

# Known placeholders -> safe dummy values. Values are single-line tokens so that
# substituting them (whether the placeholder sits inline in a directive or alone
# on its own line as a whole shell block) always yields syntactically valid bash.
# Block-style placeholders (hooks, module loads, env activation) get a no-op `:`
# or a harmless single command so `bash -n` stays clean.
KNOWN_DUMMIES: Dict[str, str] = {
    # ---- scheduler / resource knobs (inline in #SBATCH lines) ----
    "CASE_NAME": "a2mc_dummy_case",
    "ACCOUNT": "m0000",
    "QUEUE": "shared",
    "NODES": "1",
    "MPI_RANKS": "1",
    "TASKS_PER_NODE": "1",
    "CPUS_PER_TASK": "4",
    "OMP_NUM_THREADS": "1",
    "WALLTIME": "00:30:00",
    "OUTPUT_DIR": "/tmp/a2mc_dummy_out",
    # ---- paths / commands (inline) ----
    "MODEL_BINARY": "/tmp/a2mc_dummy/model.x",
    "RUN_CMD": "/tmp/a2mc_dummy/run.nml",
    "MPI_LAUNCHER": "srun",
    "PYTHON_INVOKE": "python driver.py",
    "CREATE_CASE_CMD": "true",
    # ---- block-style placeholders (own line; may be multi-command at run time) ----
    "MODULES": ":  # dummy module block",
    "PRE_RUN_HOOK": ":  # dummy pre-run hook",
    "POST_RUN_HOOK": ":  # dummy post-run hook",
    "PYTHON_ENV_ACTIVATE": ":  # dummy env-activate block",
    # ---- generic skeleton tokens from _template (illustrative placeholders) ----
    "PLACEHOLDER": "dummy_value",
    "PLACEHOLDERS": "dummy_value",
    "VARNAME": "DUMMY_VAR",
}

# Fallback for any placeholder not in KNOWN_DUMMIES. A bareword token is a valid
# bash command-name / word in every context, so `bash -n` still passes; the
# unknown token is reported as a WARN so the adapter author enumerates it.
GENERIC_DUMMY = "A2MC_UNKNOWN_PLACEHOLDER"


# =============================================================================
# Result types
# =============================================================================

@dataclass
class TemplateResult:
    """Outcome of validating one run template."""
    path: Path
    placeholders: List[str] = field(default_factory=list)      # sorted unique
    unknown_placeholders: List[str] = field(default_factory=list)
    is_slurm: bool = False
    present_directives: List[str] = field(default_factory=list)
    missing_directives: List[str] = field(default_factory=list)
    has_model_binary: bool = False
    bash_ok: Optional[bool] = None
    bash_error: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.bash_ok is False or self.missing_directives:
            return "FAIL"
        if self.unknown_placeholders:
            return "WARN"
        return "PASS"


# =============================================================================
# Core checks
# =============================================================================

def enumerate_placeholders(text: str) -> List[str]:
    """Return the sorted, unique list of `{{PLACEHOLDER}}` names in `text`."""
    return sorted(set(PLACEHOLDER_RE.findall(text)))


def render_with_dummies(text: str) -> str:
    """Substitute every `{{PLACEHOLDER}}` with a dummy value.

    Known placeholders use their registry dummy; unknown ones use GENERIC_DUMMY.
    """
    def _sub(m: re.Match) -> str:
        name = m.group(1)
        return KNOWN_DUMMIES.get(name, GENERIC_DUMMY)

    return PLACEHOLDER_RE.sub(_sub, text)


def check_bash_syntax(rendered: str) -> tuple[bool, str]:
    """Write `rendered` to a temp file and run `bash -n`. Returns (ok, stderr)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(rendered)
        tmp_path = fh.name
    try:
        proc = subprocess.run(
            ["bash", "-n", tmp_path],
            capture_output=True, text=True, check=False,
        )
        ok = proc.returncode == 0
        err = proc.stderr.strip().replace(tmp_path, "<rendered>")
        return ok, err
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass


def find_sbatch_directives(text: str) -> List[str]:
    """Return the set of `#SBATCH --<name>` directive names present in `text`."""
    found = []
    for m in re.finditer(r"^\s*#SBATCH\s+--([A-Za-z0-9-]+)", text, re.MULTILINE):
        found.append(m.group(1))
    return found


def validate_template(path: Path) -> TemplateResult:
    """Run all four checks on one template file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    result = TemplateResult(path=path)

    # Check 1 — RENDER / placeholder inventory
    result.placeholders = enumerate_placeholders(text)
    result.unknown_placeholders = [
        p for p in result.placeholders if p not in KNOWN_DUMMIES
    ]

    # Check 3 — scheduler directives (detect Slurm by any #SBATCH line)
    directives = find_sbatch_directives(text)
    result.is_slurm = bool(directives)
    if result.is_slurm:
        for req in REQUIRED_SBATCH_DIRECTIVES:
            if req in directives:
                result.present_directives.append(req)
            else:
                result.missing_directives.append(req)
    else:
        result.notes.append(
            "no #SBATCH directives found — treated as a non-scheduler "
            "(local) template; directive check skipped"
        )

    # Check 4 — MODEL_BINARY note
    result.has_model_binary = MODEL_BINARY_PLACEHOLDER in result.placeholders
    if result.has_model_binary:
        result.notes.append(
            f"{{{{{MODEL_BINARY_PLACEHOLDER}}}}} present — at run time it MUST "
            "resolve to an executable file (renderer/ensemble generator should "
            "verify `-x` before submit)"
        )

    # Check 2 — SYNTAX (bash -n on the rendered script)
    rendered = render_with_dummies(text)
    ok, err = check_bash_syntax(rendered)
    result.bash_ok = ok
    result.bash_error = err

    return result


# =============================================================================
# Model dispatch (via ModelSpec / registry)
# =============================================================================

def load_spec(model_name: str):
    """Import the adapter package and return its ModelSpec via the registry.

    Returns None if the model can't be loaded (the caller reports the reason).
    """
    import importlib
    importlib.import_module(f"models.{model_name}")
    from models import registry
    backend = registry.get_model(model_name)
    return backend.spec


# =============================================================================
# Reporting
# =============================================================================

def print_report(model_name: str, display_name: str, results: List[TemplateResult]) -> None:
    print(f"\nRun-template validator (V5) — model: {model_name} ({display_name})")
    print(f"  templates dir: models/{model_name}/runtemplates/")
    print(f"  templates found: {len(results)}")
    print("")

    for r in results:
        rel = r.path.relative_to(REPO_ROOT)
        print(f"=== {rel.name}  ->  {r.verdict} ===")
        print(f"  path: {rel}")

        # Placeholder inventory
        print(f"  placeholders ({len(r.placeholders)}): "
              f"{', '.join(r.placeholders) if r.placeholders else '(none)'}")
        if r.unknown_placeholders:
            print(f"    WARN unknown placeholder(s) (rendered with generic dummy): "
                  f"{', '.join(r.unknown_placeholders)}")

        # Scheduler directives
        if r.is_slurm:
            print(f"  slurm directives present: "
                  f"{', '.join('--' + d for d in r.present_directives) or '(none)'}")
            if r.missing_directives:
                print(f"    FAIL missing required directive(s): "
                      f"{', '.join('--' + d for d in r.missing_directives)}")
        else:
            print("  slurm: no #SBATCH directives (local template) — directive check skipped")

        # bash -n
        if r.bash_ok:
            print("  bash -n: PASS (rendered script is syntactically valid)")
        else:
            print("  bash -n: FAIL")
            for line in (r.bash_error or "(no stderr)").splitlines():
                print(f"    {line}")

        # Notes
        for note in r.notes:
            print(f"  note: {note}")
        print("")


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(
        description="V5 — validate an adapter's HPC run template(s).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--model", required=True,
                   help="Adapter directory name under models/ (e.g., 'ecosim')")
    p.add_argument("--template", default=None,
                   help="Validate only this template filename (default: all *.tmpl)")
    args = p.parse_args()

    # bash must be available for the syntax check.
    if shutil.which("bash") is None:
        print("ERROR: `bash` not found on PATH — cannot run the syntax check.",
              file=sys.stderr)
        return 3

    adapter_path = REPO_ROOT / "models" / args.model
    if not adapter_path.is_dir():
        print(f"ERROR: adapter directory not found: {adapter_path}", file=sys.stderr)
        return 3

    # Model dispatch: load the ModelSpec (confirms the adapter is registered).
    try:
        spec = load_spec(args.model)
        display_name = spec.display_name
    except Exception as e:
        print(f"ERROR: could not load ModelSpec for {args.model!r}: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return 3

    runtemplates_dir = adapter_path / "runtemplates"
    if not runtemplates_dir.is_dir():
        print(f"ERROR: no runtemplates/ directory: {runtemplates_dir}", file=sys.stderr)
        return 3

    if args.template:
        candidates = [runtemplates_dir / args.template]
        if not candidates[0].is_file():
            print(f"ERROR: template not found: {candidates[0]}", file=sys.stderr)
            return 3
    else:
        candidates = sorted(runtemplates_dir.glob("*.tmpl"))

    if not candidates:
        print(f"ERROR: no *.tmpl files in {runtemplates_dir}", file=sys.stderr)
        return 3

    results = [validate_template(t) for t in candidates]
    print_report(args.model, display_name, results)

    verdicts = [r.verdict for r in results]
    n_pass = verdicts.count("PASS")
    n_warn = verdicts.count("WARN")
    n_fail = verdicts.count("FAIL")
    print(f"Summary: {n_pass} PASS, {n_warn} WARN, {n_fail} FAIL "
          f"(of {len(results)} template(s))")

    if n_fail:
        return 2
    if n_warn:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
