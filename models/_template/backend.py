"""Template ModelBackend — copy + fill in for your model.

Implements the eight abstract methods from `models/base.py:ModelBackend`. This
template stubs each with `NotImplementedError` carrying a clear pointer back
here. After copying:

    1. Rename `TemplateBackend` → `<YourModel>Backend`
    2. Replace each TODO with a real implementation
    3. The `spec` class attribute should reference your renamed
       `<YOURMODEL>_SPEC` from spec.py

The framework calls these methods. It does NOT know what's inside — for FATES,
`create_case()` shells out to `tools/create_case.sh`; for EcoSim, it might
invoke a Python launcher; for an HPC job-script-driven model, it might just
fill in a template + sbatch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import ModelBackend
from .spec import TEMPLATE_SPEC


class TemplateBackend(ModelBackend):
    """Stub backend. Every method raises NotImplementedError."""

    spec = TEMPLATE_SPEC

    # ---- Parameter and output parsing ----
    #
    # These two methods are typically thin wrappers over the parser classes
    # declared in spec.py. The framework's V1/V2 validators dispatch through
    # spec.parameter_parser_class / spec.output_parser_class directly, so
    # backend wrappers are only used for non-validation calls (e.g., the
    # orchestrator reading the parameter file at runtime).

    def parse_parameters(self, param_file: Path) -> Dict[str, Any]:
        # TODO(adapter-kit): typically: return self.spec.parameter_parser_class().parse(param_file)
        raise NotImplementedError(
            f"TemplateBackend.parse_parameters({param_file}) is a stub. "
            f"Wire it to your parameter_parser_class.parse(). "
            f"See models/_template/backend.py."
        )

    def parse_outputs(self, output_cdl: Path) -> Dict[str, Any]:
        # TODO(adapter-kit): typically: return self.spec.output_parser_class().parse(output_cdl)
        raise NotImplementedError(
            f"TemplateBackend.parse_outputs({output_cdl}) is a stub. "
            f"Wire it to your output_parser_class.parse()."
        )

    # ---- Parameter file I/O ----

    def write_parameter_file(
        self,
        base_param_file: Path,
        modifications: Dict[str, Any],
        output_path: Path,
    ) -> None:
        # TODO(adapter-kit): apply `modifications` (param_name → new value) to
        # `base_param_file` and write to `output_path`. Use ncdump+ncgen for CDL,
        # in-memory netCDF4 lib for direct .nc, json.dump for JSON, etc.
        raise NotImplementedError(
            f"TemplateBackend.write_parameter_file is a stub. "
            f"Implement modification-application for your model's parameter file format."
        )

    # ---- Case creation and submission ----

    def create_case(
        self,
        case_name: str,
        param_file: Path,
        config: Dict[str, Any],
    ) -> Path:
        # TODO(adapter-kit): create a model run case directory with:
        #   - the modified parameter file linked or copied in
        #   - the run-template script (rendered from runtemplates/) installed
        #   - any case-specific config (namelist, ATS XML, etc.)
        # Return the case path.
        raise NotImplementedError(
            f"TemplateBackend.create_case({case_name}) is a stub. "
            f"Adapt your model's case-setup workflow into this method. "
            f"See use_cases/<site>/scripts/ for the rendered run template."
        )

    def submit_ensemble(
        self,
        case_paths: List[Path],
        config: Dict[str, Any],
    ) -> List[str]:
        # TODO(adapter-kit): submit each case to the scheduler. For HPC variants,
        # this is `sbatch <case>/submit.sh` per case. For local, run sequentially
        # or in parallel via subprocess.Popen. Return job IDs (real or synthetic).
        raise NotImplementedError(
            f"TemplateBackend.submit_ensemble (n={len(case_paths)}) is a stub. "
            f"Wire it to your scheduler's submit command."
        )

    def check_case_status(self, case_path: Path) -> str:
        # TODO(adapter-kit): query scheduler for job status, OR inspect case
        # directory for completion markers (e.g., a 'COMPLETED' file written
        # by the run script's exit hook). Return one of:
        # 'PENDING' / 'RUNNING' / 'COMPLETED' / 'FAILED'.
        raise NotImplementedError(
            f"TemplateBackend.check_case_status({case_path}) is a stub."
        )

    # ---- Output extraction ----

    def extract_history_variables(
        self,
        case_path: Path,
        variables: List[str],
        time_range: Optional[tuple] = None,
        tape: str = "h0",
    ) -> Any:
        # TODO(adapter-kit): open the case's history NetCDF (or other format),
        # subset the requested variables, return as xarray.Dataset (or dict
        # of arrays — adapter-defined). The framework treats the return value
        # opaquely until a generic extraction layer is defined. `tape` selects
        # among multiple history outputs if your model has more than one (e.g.
        # EcoSIM's daily/hourly hist_fincl1/hist_fincl2 tapes); ignore it if not.
        raise NotImplementedError(
            f"TemplateBackend.extract_history_variables (vars={variables}) is a stub."
        )

    # ---- Diagnostic tooling ----

    def list_diagnostic_tools(self) -> List[Path]:
        # TODO(adapter-kit): return paths to model-specific test_*.py scripts
        # under your adapter directory (or anywhere the orchestrator can find
        # them). Phase 3 of A2MC's calibration workflow auto-discovers these
        # for hypothesis testing.
        return []  # safe default: no model-specific diagnostics yet
