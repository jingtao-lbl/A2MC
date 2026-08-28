"""ATS ModelBackend.

Drives ATS as a standalone executable: one working directory per ensemble member, each
running ``ats <case>.xml`` (MPI) and producing HDF5/XDMF visualization + comma-delimited
observation ``.dat`` files.

Implementation status (v0.1, standalone target):
    * parse_parameters / parse_outputs / write_parameter_file  — COMPLETE (XML in/out).
    * create_case / submit_ensemble / check_case_status / extract_history_variables
      — functional-minimal: they encode the real ATS run shape (stage deck, srun ats,
      completion markers, .dat extraction) but the run-template + observation-injection
      polish is deferred (Yellow adapter conformance is correct at the RAG stage).

The framework never looks inside these methods; it only relies on their contract.
"""

from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import ModelBackend
from .output_parser import ATSOutputParser
from .parameter_parser import ATSParameterParser, set_parameter_values
from .spec import ATS_SPEC


class ATSBackend(ModelBackend):
    """Standalone-ATS backend. Parameter/output I/O is complete; run wiring is v0.1."""

    spec = ATS_SPEC

    # ---- Parameter and output parsing ----

    def parse_parameters(self, param_file: Path) -> Dict[str, Any]:
        return ATSParameterParser().parse(Path(param_file))

    def parse_outputs(self, output_cdl: Path) -> Dict[str, Any]:
        return ATSOutputParser().parse(Path(output_cdl))

    # ---- Parameter file I/O ----

    def write_parameter_file(
        self,
        base_param_file: Path,
        modifications: Dict[str, Any],
        output_path: Path,
        surface: str = "primary",
    ) -> None:
        """Apply ``{address: value}`` modifications to a base ATS XML deck and write it.

        Addresses are the ``a/b/c/leaf`` paths emitted by ATSParameterParser. Fails loud
        (ValueError) if any address is not found in the deck.
        """
        if surface != "primary":
            raise ValueError(
                f"ATS has a single (primary) parameter surface; got surface={surface!r}."
            )
        tree = ET.parse(Path(base_param_file))
        root = tree.getroot()
        missing = set_parameter_values(root, modifications)
        if missing:
            raise ValueError(
                f"write_parameter_file: {len(missing)} address(es) not found in "
                f"{base_param_file}: {sorted(missing)[:5]}"
                + (" ..." if len(missing) > 5 else "")
            )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        tree.write(Path(output_path), encoding="utf-8", xml_declaration=False)

    # ---- Case creation and submission ----

    def create_case(
        self,
        case_name: str,
        param_file: Path,
        config: Dict[str, Any],
        secondary_param_file: Optional[Path] = None,
    ) -> Path:
        """Create an ATS run directory: stage the deck as ``<case>/<case_name>.xml`` and
        render a submit script that runs ``ats`` on it.

        ``param_file`` is the (already parameter-modified) ATS XML deck. ``config`` supplies
        run settings; recognized keys (all optional, sensible defaults):
            A2MC_CASE_ROOT / case_root  — parent dir for cases (default: cwd/cases)
            A2MC_ATS_EXE / ats_exe      — the ats executable (default: "ats")
            A2MC_MPI_LAUNCH / mpi_launch— e.g. "srun -n 8" or "mpirun -np 4" (default: "")
        """
        case_root = Path(config.get("A2MC_CASE_ROOT") or config.get("case_root") or "cases")
        case_dir = case_root / case_name
        case_dir.mkdir(parents=True, exist_ok=True)

        deck_dst = case_dir / f"{case_name}.xml"
        shutil.copyfile(Path(param_file), deck_dst)

        ats_exe = config.get("A2MC_ATS_EXE") or config.get("ats_exe") or "ats"
        launch = config.get("A2MC_MPI_LAUNCH") or config.get("mpi_launch") or ""
        run_cmd = f"{launch} {ats_exe} {deck_dst.name}".strip()

        submit = case_dir / "submit.sh"
        submit.write_text(
            "#!/bin/bash\n"
            "# A2MC ATS case run script (v0.1). Runs ATS on the staged deck.\n"
            f"cd \"$(dirname \"$0\")\"\n"
            f"{run_cmd}\n"
            "rc=$?\n"
            'if [ $rc -eq 0 ]; then touch A2MC_COMPLETED; else touch A2MC_FAILED; fi\n'
            "exit $rc\n"
        )
        submit.chmod(0o755)
        return case_dir

    def submit_ensemble(
        self,
        case_paths: List[Path],
        config: Dict[str, Any],
    ) -> List[str]:
        """Submit each case. If a scheduler submit command is configured
        (``A2MC_SUBMIT_CMD``, e.g. "sbatch"), use it; otherwise run ``submit.sh`` locally
        in the background and return the PID as a synthetic job id.
        """
        submit_cmd = config.get("A2MC_SUBMIT_CMD") or config.get("submit_cmd")
        job_ids: List[str] = []
        for case_dir in case_paths:
            script = Path(case_dir) / "submit.sh"
            if submit_cmd:
                out = subprocess.run(
                    [*submit_cmd.split(), str(script)],
                    capture_output=True, text=True, cwd=str(case_dir),
                )
                job_ids.append(out.stdout.strip() or f"submit-error:{case_dir}")
            else:
                proc = subprocess.Popen(["bash", str(script)], cwd=str(case_dir))
                job_ids.append(f"local:{proc.pid}")
        return job_ids

    def check_case_status(self, case_path: Path) -> str:
        case_path = Path(case_path)
        if (case_path / "A2MC_COMPLETED").exists():
            return "COMPLETED"
        if (case_path / "A2MC_FAILED").exists():
            return "FAILED"
        # A staged-but-unstarted case has a submit script but no marker.
        if (case_path / "submit.sh").exists():
            return "PENDING"
        return "PENDING"

    # ---- Output extraction ----

    def extract_history_variables(
        self,
        case_path: Path,
        variables: List[str],
        time_range: Optional[tuple] = None,
        tape: str = "h0",
    ) -> Dict[str, Any]:
        """Read requested observation series from the case's ``.dat`` file(s).

        ``tape`` is IGNORED: ATS writes a single observation output, no multi-tape concept
        (accepted only for signature parity with the model-agnostic caller,
        ``tools/model_evaluate_case.py``).

        Returns ``{variable_name: numpy.ndarray}`` plus a ``"time"`` key when a time column
        is present. Best-effort: matches requested names against the ``.dat`` header columns
        (unit brackets stripped). ATS must have been asked to observe these (deck observations
        block) or they will be absent.
        """
        import numpy as np

        case_path = Path(case_path)
        dat_files = sorted(case_path.glob("*.dat"))
        result: Dict[str, Any] = {}
        for dat in dat_files:
            # Column names (strip units) in file order.
            cols = list(ATSOutputParser().parse(dat).keys())
            # Load numeric rows.
            try:
                data = np.genfromtxt(dat, delimiter=",", comments="#")
            except (OSError, ValueError):
                continue
            if data.ndim == 1:
                data = data.reshape(1, -1)
            n = min(len(cols), data.shape[1])
            colmap = {cols[i]: data[:, i] for i in range(n)}
            # Time column heuristic.
            for tkey in ("time", "cycle", "time [s]"):
                if tkey in colmap and "time" not in result:
                    result["time"] = colmap[tkey]
            for v in variables:
                if v in colmap:
                    result[v] = colmap[v]
        return result

    # ---- Diagnostic tooling ----

    def list_diagnostic_tools(self) -> List[Path]:
        tools_dir = Path(__file__).parent / "tools"
        if not tools_dir.exists():
            return []
        return sorted(tools_dir.glob("test_*.py"))
