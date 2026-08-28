#!/usr/bin/env python3
"""
init_adapter.py - Walk a new modeler through the A2MC adapter pipeline.

The CLI scaffold per `docs/19_Adapter_Kit_Implementation_Plan.md` §6.3.
14 steps in 3 phases (A scaffold, B knowledge pipeline, C execution setup).

This is the Step C implementation — only Steps 1, 2, 11 (stub), 14 are wired.
Steps 3-10, 12, 13 print "TODO: implemented in Step D/E" and exit cleanly.

Usage:
    python scripts/init_adapter.py --model ecosim
    python scripts/init_adapter.py --model ecosim --restart-from 2
    python scripts/init_adapter.py --model ecosim --param-file path/to/params.cdl

State persists to `.adapter-kit-state-<model>.json` in the repo root.
Resuming picks up from the first incomplete step unless --restart-from forces.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# =============================================================================
# Setup
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "models" / "_template"

# Steps 1-14 per Doc 19 §6.3
ALL_STEPS = list(range(1, 15))

# Steps wired in this Step C implementation. Others print a placeholder + exit.
WIRED_STEPS = {1, 2, 11, 14}


# =============================================================================
# Name normalization
# =============================================================================

def to_capwords(name: str) -> str:
    """`ecosim` -> `Ecosim`; `elm_cn` -> `ElmCn`."""
    return "".join(part.capitalize() for part in name.split("_") if part)


def to_upper_snake(name: str) -> str:
    """`ecosim` -> `ECOSIM`; `elm_cn` -> `ELM_CN`."""
    return name.upper()


def validate_model_name(name: str) -> str:
    """Normalize + validate. Raises ValueError on bad name."""
    if not name:
        raise ValueError("model name is empty")
    if name.startswith("_"):
        raise ValueError(
            f"model name {name!r} starts with underscore. "
            f"Underscore-prefix is reserved for the framework's `_template` adapter."
        )
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError(
            f"model name {name!r} must match [a-z][a-z0-9_]* "
            f"(lowercase letters, digits, underscores; first char letter)."
        )
    return name


# =============================================================================
# State file
# =============================================================================

@dataclass
class StepResult:
    status: str = "pending"           # 'pending' | 'in_progress' | 'completed' | 'failed' | 'skipped'
    timestamp: str = ""
    notes: str = ""
    verdict: str = ""                  # for validator steps: 'Green' | 'Yellow' | 'Red'
    report_path: str = ""              # path to report file if applicable


@dataclass
class State:
    model: str
    created_at: str = ""
    updated_at: str = ""
    step_results: Dict[int, StepResult] = field(default_factory=dict)

    def get(self, step: int) -> StepResult:
        return self.step_results.setdefault(step, StepResult())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "step_results": {
                str(k): {
                    "status": v.status,
                    "timestamp": v.timestamp,
                    "notes": v.notes,
                    "verdict": v.verdict,
                    "report_path": v.report_path,
                }
                for k, v in self.step_results.items()
            },
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "State":
        st = cls(model=d["model"])
        st.created_at = d.get("created_at", "")
        st.updated_at = d.get("updated_at", "")
        for k, v in d.get("step_results", {}).items():
            st.step_results[int(k)] = StepResult(
                status=v.get("status", "pending"),
                timestamp=v.get("timestamp", ""),
                notes=v.get("notes", ""),
                verdict=v.get("verdict", ""),
                report_path=v.get("report_path", ""),
            )
        return st


def state_path(model: str) -> Path:
    return REPO_ROOT / f".adapter-kit-state-{model}.json"


def load_state(model: str) -> State:
    p = state_path(model)
    if p.is_file():
        return State.from_dict(json.loads(p.read_text()))
    state = State(
        model=model,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return state


def save_state(state: State) -> None:
    state.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state_path(state.model).write_text(json.dumps(state.to_dict(), indent=2) + "\n")


def mark_step(state: State, step: int, status: str, **kwargs) -> None:
    r = state.get(step)
    r.status = status
    r.timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for k, v in kwargs.items():
        setattr(r, k, v)
    save_state(state)


# =============================================================================
# Step 1 — Scaffold adapter directory
# =============================================================================

# Files we apply text rewrites to. Other files (binary, etc.) are copied as-is.
REWRITE_SUFFIXES = {".py", ".yaml", ".yml", ".md", ".tmpl", ".sh", ".txt"}


def step_1_scaffold(state: State, model: str, dry_run: bool = False) -> None:
    """Copy `models/_template/` to `models/<model>/` with class-name rewrites."""
    print(f"\n=== Step 1: Scaffold adapter directory ===")
    dest = REPO_ROOT / "models" / model

    if dest.exists():
        print(f"  [WARN] {dest.relative_to(REPO_ROOT)} already exists.")
        print(f"         Skipping copy. To re-scaffold, delete it first:")
        print(f"             rm -rf {dest}")
        mark_step(state, 1, "completed", notes="adapter dir already existed; skipped copy")
        return

    print(f"  source: {TEMPLATE_PATH.relative_to(REPO_ROOT)}")
    print(f"  dest:   {dest.relative_to(REPO_ROOT)}")
    print(f"  rewrites:")
    print(f"    'Template'   -> {to_capwords(model)!r}")
    print(f"    'TEMPLATE'   -> {to_upper_snake(model)!r}")
    print(f"    '_template'  -> {model!r}")

    if dry_run:
        print(f"  [DRY-RUN] would copy + rewrite. Skipping.")
        mark_step(state, 1, "skipped", notes="dry-run")
        return

    shutil.copytree(TEMPLATE_PATH, dest)

    # Apply rewrites file-by-file
    capwords = to_capwords(model)
    upper = to_upper_snake(model)

    # Skip pyc / pycache
    skip_dirs = {"__pycache__"}

    n_rewritten = 0
    for path in dest.rglob("*"):
        if any(part in skip_dirs for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix not in REWRITE_SUFFIXES:
            continue

        text = path.read_text()
        new_text = (
            text.replace("Template", capwords)
                .replace("TEMPLATE", upper)
                .replace("_template", model)
        )
        if new_text != text:
            path.write_text(new_text)
            n_rewritten += 1

    print(f"  rewrote {n_rewritten} file(s) under {dest.relative_to(REPO_ROOT)}")
    mark_step(state, 1, "completed", notes=f"scaffolded; {n_rewritten} files rewritten")


# =============================================================================
# Step 2 — Adapter conformance validator (V4)
# =============================================================================

def step_2_v4_conformance(
    state: State,
    model: str,
    param_file: Optional[Path],
    output_cdl: Optional[Path],
    no_iterate: bool,
) -> str:
    """Run V4 against the new adapter; return verdict ('Green'|'Yellow'|'Red')."""
    print(f"\n=== Step 2: Adapter conformance validator (V4) ===")

    # Run V4 as subprocess so it imports cleanly via its own bootstrap
    cmd = [
        sys.executable,
        str(REPO_ROOT / "tools" / "adapter_conformance_validator.py"),
        "--model", model,
        "--quiet",
    ]
    if param_file:
        cmd += ["--param-file", str(param_file)]
    if output_cdl:
        cmd += ["--output-cdl", str(output_cdl)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)

    verdict_map = {0: "Green", 1: "Yellow", 2: "Red"}
    verdict = verdict_map.get(result.returncode, "Error")
    report_path = REPO_ROOT / "docs" / "a2mc_reference" / f"adapter_conformance_{model}.md"

    print(f"  verdict: {verdict}")
    print(f"  report:  {report_path.relative_to(REPO_ROOT) if report_path.exists() else '(no report written)'}")

    mark_step(
        state, 2,
        "completed" if verdict in ("Green", "Yellow") else "failed",
        verdict=verdict,
        report_path=str(report_path.relative_to(REPO_ROOT)),
    )

    return verdict


# =============================================================================
# Steps 3-10, 12, 13 — placeholders for Step D/E
# =============================================================================

PHASE_B_KNOWLEDGE_STEPS = {
    3: ("Wiki acquisition", "docs/a2mc_reference/codebase_wiki_generation_roadmap.md"),
    4: ("Codebase wiki validator (V1)", "tools/codebase_wiki_validator.py"),
    5: ("Param/output file extraction", "ncdump -h on user's NetCDF files"),
    6: ("Parser regex injection", "models/<model>/parameter_parser.py + output_parser.py"),
    7: ("Curated seed (Recipe G1)", "scripts/curated_seed_builder.py — Step D"),
    8: ("YAML wiki validator (V2)", "tools/yaml_wiki_validator.py"),
    9: ("RAG build", "scripts/build_rag_index.py + register milestone — Step E"),
    10: ("Memory seeding", "memory/<model>/gained_knowledge/ — Step E"),
}
PHASE_C_EXECUTION_STEPS = {
    12: ("Run template validator (V5)", "tools/run_template_validator.py — Step E"),
    13: ("Smoke test", "orchestrator dry-run phases 0-2 — Step E"),
}


def step_placeholder(state: State, step: int, name: str, hint: str) -> None:
    """Stub for steps not yet implemented."""
    print(f"\n=== Step {step}: {name} ===")
    print(f"  [STUB] not yet implemented in init_adapter.py.")
    print(f"  Hint: {hint}")
    print(f"  Implementation arrives in Doc 19 §10 Step D or Step E.")
    mark_step(state, step, "skipped", notes="stub — pending Step D/E")


# =============================================================================
# Step 11 — Run template select + render (basic stub for Step C)
# =============================================================================

RUN_TEMPLATE_VARIANTS = [
    ("hpc_cime", "HPC + CIME (ELM/CESM/E3SM)"),
    ("hpc_standalone", "HPC + standalone binary (EcoSIM-like)"),
    ("hpc_python", "HPC + Python script/library"),
    ("local_cime", "Local + CIME (rare)"),
    ("local_standalone", "Local + standalone binary"),
    ("local_python", "Local + Python script/library"),
]


def step_11_run_template(state: State, model: str, dry_run: bool = False) -> None:
    """List runtemplate variants for the user. Actual rendering arrives in Step E."""
    print(f"\n=== Step 11: Run template selection (preview) ===")
    print(f"  Available templates under models/{model}/runtemplates/:")
    for code, desc in RUN_TEMPLATE_VARIANTS:
        path = REPO_ROOT / "models" / model / "runtemplates" / f"{code}.sh.tmpl"
        marker = "✓" if path.is_file() else "✗"
        print(f"    [{marker}] {code:18s}  {desc}")
    print(f"")
    print(f"  [STUB] interactive variant selection + {{VAR}} rendering is in Step E.")
    print(f"  For now: pick one manually and edit it to fit your scheduler / modules / queue.")

    mark_step(state, 11, "skipped", notes="preview only; full render in Step E")


# =============================================================================
# Step 14 — Next-steps printout
# =============================================================================

def step_14_next_steps(state: State, model: str) -> None:
    """Print actionable next steps based on the current state."""
    print(f"\n=== Step 14: Next steps ===")

    completed = sorted(s for s, r in state.step_results.items() if r.status == "completed")
    skipped = sorted(s for s, r in state.step_results.items() if r.status == "skipped")
    failed = sorted(s for s, r in state.step_results.items() if r.status == "failed")

    print(f"")
    print(f"  Adapter:  models/{model}/")
    print(f"  Status:   completed={completed}  skipped={skipped}  failed={failed}")
    print(f"")
    print(f"  Resume:   python scripts/init_adapter.py --model {model}")
    print(f"  Restart:  python scripts/init_adapter.py --model {model} --restart-from <step>")
    print(f"")
    print(f"  Continuing from where this scaffold leaves off:")
    print(f"")
    print(f"  1. Open models/{model}/ and resolve the # TODO(adapter-kit): markers.")
    print(f"     The V4 report at docs/a2mc_reference/adapter_conformance_{model}.md")
    print(f"     enumerates them with file:line.")
    print(f"")
    print(f"  2. Generate your model's wiki at a pinned commit (Step 3 + 4):")
    print(f"        See docs/a2mc_reference/codebase_wiki_generation_roadmap.md")
    print(f"")
    print(f"  3. Author your curated YAML (Step 7) — Step D of the kit's plan:")
    print(f"        See docs/a2mc_reference/graphrag_curated_yaml_roadmap.md")
    print(f"")
    print(f"  4. Build the RAG and register the milestone (Step 9) — Step E of the plan:")
    print(f"        See docs/a2mc_reference/rag_build_roadmap.md")
    print(f"        See docs/a2mc_reference/version_association_workflow.md")
    print(f"")
    print(f"  See `docs/19_Adapter_Kit_Implementation_Plan.md` for the full pipeline.")
    print(f"")

    mark_step(state, 14, "completed")


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    p = argparse.ArgumentParser(
        description="A2MC adapter kit CLI scaffold (Doc 19 §6.3).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--model", required=True, help="Adapter directory name (lowercase; e.g., 'ecosim')")
    p.add_argument(
        "--restart-from", type=int, default=None,
        help="Restart at this step number (1-14). Earlier steps marked completed.",
    )
    p.add_argument("--param-file", type=Path, help="Parameter file path (used by V4 Dim 5)")
    p.add_argument("--output-cdl", type=Path, help="Output CDL path (used by V4 Dim 6)")
    p.add_argument("--no-iterate", action="store_true", help="Don't loop on validator Yellow/Red")
    p.add_argument("--dry-run", action="store_true", help="Print what would happen without changing files")

    args = p.parse_args()

    try:
        model = validate_model_name(args.model)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    state = load_state(model)

    if args.restart_from is not None:
        if args.restart_from < 1 or args.restart_from > 14:
            print(f"ERROR: --restart-from must be 1-14, got {args.restart_from}", file=sys.stderr)
            return 2
        # Mark earlier steps completed (don't re-run them); clear later steps
        for s in ALL_STEPS:
            if s < args.restart_from:
                if state.get(s).status == "pending":
                    mark_step(state, s, "skipped", notes="--restart-from skipped")
            else:
                state.step_results[s] = StepResult(status="pending")
        save_state(state)
        print(f"Restarting from step {args.restart_from}")

    print(f"=========================================================")
    print(f" A2MC adapter kit — initializing {model!r}")
    print(f" State file: {state_path(model).relative_to(REPO_ROOT)}")
    print(f"=========================================================")

    # ---- Step 1: Scaffold ----
    if state.get(1).status not in ("completed", "skipped"):
        step_1_scaffold(state, model, dry_run=args.dry_run)
    else:
        print(f"\n[Step 1 already {state.get(1).status} — skipping. --restart-from 1 to redo.]")

    # ---- Step 2: V4 conformance ----
    if state.get(2).status not in ("completed", "skipped"):
        verdict = step_2_v4_conformance(
            state, model,
            param_file=args.param_file,
            output_cdl=args.output_cdl,
            no_iterate=args.no_iterate,
        )
        if verdict == "Red":
            print(f"\n[Step 2 returned Red. Halting per validator-iteration semantics (Doc 19 §6.5).]")
            print(f"Fix the issues in the V4 report, then re-run:")
            print(f"    python scripts/init_adapter.py --model {model} --restart-from 2")
            return 2
    else:
        print(f"\n[Step 2 already {state.get(2).status} — skipping.]")

    # ---- Steps 3-10: Phase B placeholders ----
    for step in sorted(PHASE_B_KNOWLEDGE_STEPS.keys()):
        if state.get(step).status in ("completed", "skipped"):
            continue
        name, hint = PHASE_B_KNOWLEDGE_STEPS[step]
        step_placeholder(state, step, name, hint)

    # ---- Step 11: run-template preview ----
    if state.get(11).status not in ("completed", "skipped"):
        step_11_run_template(state, model, dry_run=args.dry_run)

    # ---- Steps 12-13: Phase C placeholders ----
    for step in sorted(PHASE_C_EXECUTION_STEPS.keys()):
        if state.get(step).status in ("completed", "skipped"):
            continue
        name, hint = PHASE_C_EXECUTION_STEPS[step]
        step_placeholder(state, step, name, hint)

    # ---- Step 14: Next steps ----
    step_14_next_steps(state, model)

    print(f"\nDone. State saved to {state_path(model).relative_to(REPO_ROOT)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
