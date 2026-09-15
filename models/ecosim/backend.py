"""EcoSIM ModelBackend.

Parsing methods run against the real EcoSIM parsers. The execution methods are
implemented for the **standalone serial-binary** run model proven in the BioCON
test1_ex1 reproduction (`memory/dev_logs_adapterkit/20260711c_*`): EcoSIM is a
serial Fortran binary invoked as ``ecosim.f90.x <runfile.nml>`` whose calibration
surface is the PFT input NetCDF (``ds_input__pft_test__*.nc``). There is no CIME.

Run-config contract (keys read from the merged machine+site ``config`` dict, all
optional with sensible fallbacks):

    A2MC_ECOSIM_BINARY        path to ecosim.f90.x            (required for a real run)
    A2MC_ECOSIM_BASE_NAMELIST base EcoSIM runfile .nml to stage + repoint
    A2MC_EXEC_MODE            'hpc' (default) or 'local'      — 'local' runs the cases as
                              background processes on this machine instead of sbatch-ing
                              them, for a workstation with no scheduler. Purely additive:
                              unset or 'hpc' reaches none of the local code.
    A2MC_LOCAL_WORKERS        local mode only — how many cases run at once
                              (default: min(4, cpu_count))
    A2MC_ECOSIM_RUNTEMPLATE   submit-script template          (default: this package's
                              hpc_standalone.sh.tmpl, or local_serial.sh.tmpl in local mode)
    A2MC_OUTPUT_DIR           ensemble output root            (default: cwd/ecosim_runs)
    A2MC_HPC_ACCOUNT          slurm account                   (default: m5199)
    A2MC_HPC_QUEUE            slurm qos                       (default: shared)
    A2MC_HPC_WALLTIME         slurm --time                    (default: 02:00:00)
    A2MC_DRY_RUN              if truthy, submit_ensemble stages but does NOT sbatch
                              (returns synthetic DRYRUN-* ids) — used by the e2e test

``write_parameter_file`` and ``extract_history_variables`` are fully functional and
exercised by the end-to-end smoke test (``tests/test_ecosim_backend.py``). The
scheduler-facing methods work against real Slurm and fall back to a dry-run.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import calendar
import datetime as _dt
import os
import re
import warnings
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import ModelBackend
from .spec import ECOSIM_SPEC

_PFT_AXES = ("npfts", "npft", "pft", "maxpfts")
_MOD_PFT_RE = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9_]*?)_(?P<pft>\d+)$")

# --- SECONDARY parameter surface: the EcoSIM pft_mgmt NetCDF ---
# Some params live not in the per-PFT trait NC (the primary surface) but in the
# stand-MANAGEMENT file's `pft_pltinfo` string ('01049999 <PPI> 0.005'). This is
# the ONLY EcoSIM-specific place the second surface is realized; the calibration
# layer only ever passes the generic surface name "secondary".
_PFT_MGMT_VAR = "pft_pltinfo"        # (year, ntopou, maxpfts, string128) char array
_PFT_MGMT_SLOT = 0                   # PFT slot of the calibrated plant (PFT1 = C4 grass)
_PFT_MGMT_TOKENS = {"PPI": 1}        # editable field -> whitespace-token index in the string
_PFT_MGMT_INT = {"PPI"}             # tokens written as integers (planting density = plants/m2)


def _truthy(v: Any) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")



def _exec_mode(config) -> str:
    """'hpc' (default) or 'local'. Anything unset behaves exactly as before this existed."""
    m = str(config.get("A2MC_EXEC_MODE", "") or "hpc").strip().lower()
    if m not in ("hpc", "local"):
        raise ValueError(
            "A2MC_EXEC_MODE=%r is not recognised; use 'hpc' (the default, sbatch) or "
            "'local' (background processes on this machine)." % m)
    return m


def _local_workers(config) -> int:
    """How many cases run at once locally. Conservative by default: EcoSIM is a serial
    binary, so this is a count of whole cases, and a laptop running four of them is
    already using four cores and four cases' worth of memory."""
    raw = config.get("A2MC_LOCAL_WORKERS")
    if raw:
        n = int(raw)
        if n < 1:
            raise ValueError("A2MC_LOCAL_WORKERS must be >= 1, got %r" % raw)
        return n
    return min(4, os.cpu_count() or 1)


def _dispatch_local(case_paths, workers: int, root: Path) -> int:
    """Launch the cases in the background with a concurrency cap; return the dispatcher PID.

    WHY A DETACHED DISPATCHER rather than running the cases here. `submit_ensemble` must
    RETURN so the caller can poll, exactly as it does when sbatch queues a job: the phase
    scripts, the census and `check_case_status` are all written around submission being
    non-blocking. Running the cases inline would make local mode a different workflow
    rather than the same workflow on a different machine.

    `xargs -P` supplies the worker pool, so there is no scheduler and no Python process
    that has to survive; the dispatcher is a detached shell. Its log is the thing to arm a
    Monitor on, and each case still writes its own output beside its runfile.
    """
    listing = root / "local_cases.txt"
    listing.write_text("\n".join(str(Path(c).resolve()) for c in case_paths) + "\n")
    log = root / "local_dispatch.log"

    # setsid detaches from this process group so the runs survive the session that started
    # them, which is the local equivalent of a job outliving the submitting shell.
    cmd = ("exec >>%s 2>&1; echo \"local dispatch start: $(date)  workers=%d  cases=%d\"; "
           "xargs -P %d -I{} bash -c 'cd \"{}\" && bash submit.sh' < %s; "
           "echo \"local dispatch end:   $(date)\"" % (
               shlex.quote(str(log)), workers, len(case_paths),
               workers, shlex.quote(str(listing))))
    proc = subprocess.Popen(["setsid", "bash", "-c", cmd],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL, start_new_session=True)
    return proc.pid


class EcoSIMBackend(ModelBackend):
    """EcoSIM backend for the standalone serial-binary run model."""

    spec = ECOSIM_SPEC

    # EcoSIM reads the ENTIRE runfile into a fixed-size buffer before parsing
    # (f90src/Utils/fileUtil.F90:25 `ecosim_namelist_buffer_size`) and aborts at startup
    # ("namelist_to_buffer: IO ERROR reading namelist file into buffer: 0") if the file is this
    # size or larger -- counterintuitively, hitting EOF before the buffer fills is the SUCCESS
    # path. Hit for real 2026-08-10 (memory/logs/20260810e_*.md Errata): a base namelist's own
    # comments plus long staged CFS paths pushed a generated runfile over the limit. Gate it here
    # so any future base namelist / long path combination fails loudly at case-creation time,
    # not silently at sbatch.
    _NAMELIST_BUFFER_BYTES = 4096

    # ---- Parameter and output parsing (real) ----

    def parse_parameters(self, param_file: Path) -> Dict[str, Any]:
        return self.spec.parameter_parser_class().parse(param_file)

    def parse_outputs(self, output_cdl: Path) -> Dict[str, Any]:
        return self.spec.output_parser_class().parse(output_cdl)

    # ---- Parameter-file writing (real; operates on the PFT NetCDF) ----

    def read_secondary_param(self, path, name: str) -> float:
        """Read one pft_pltinfo token back. Accepts a bare name or a canonical id, as the writer does."""
        import netCDF4 as nc
        bare = name.rsplit("_", 1)[0] if name.rsplit("_", 1)[0] in _PFT_MGMT_TOKENS else name
        if bare not in _PFT_MGMT_TOKENS:
            raise KeyError(f"secondary-surface parameter '{name}' unknown "
                           f"(known: {sorted(_PFT_MGMT_TOKENS)})")
        tok = _PFT_MGMT_TOKENS[bare]
        d = nc.Dataset(Path(path))
        try:
            pi = d.variables[_PFT_MGMT_VAR]
            s = pi[0, 0, _PFT_MGMT_SLOT].tobytes().decode("ascii", "replace").strip("\x00").strip()
            parts = s.split()
            if len(parts) <= tok:
                raise ValueError(f"pft_pltinfo has {len(parts)} tokens; need index {tok}")
            return float(parts[tok])
        finally:
            d.close()

    def secondary_param_names(self) -> set:
        """The pft_mgmt tokens this backend can write -- the SAME map `write_parameter_file`
        consumes, so a name the router accepts is a name the writer accepts."""
        return set(_PFT_MGMT_TOKENS)

    def write_parameter_file(
        self,
        base_param_file: Path,
        modifications: Dict[str, Any],
        output_path: Path,
        surface: str = "primary",
    ) -> None:
        """Copy the base parameter file and apply parameter modifications.

        ``surface`` selects which of EcoSIM's three parameter surfaces to write:
          - ``"primary"`` (default): the per-PFT trait NetCDF. ``modifications``
            keys may be a bare variable name (``VCMX`` — broadcast to every PFT
            slot if scalar, or set as the full array if a list) or a per-PFT
            shorthand ``VCMX_<pft>`` (1-based PFT index, the A2MC Morris
            convention). Raises on an unknown variable so a typo never no-ops.
          - ``"secondary"``: the stand-management pft_mgmt NetCDF. Keys are the
            editable pltinfo tokens (currently ``PPI`` = planting density). See
            ``_write_pft_mgmt_surface``.
          - ``"tertiary"``: the microbial-kinetics MicrobePars.nc (RCCZ, VMXO,
            RMOM, GO2X, and the ``nactbioms``-dimensioned SPORC/SPOMC, among
            others). Uses the SAME plain named-variable writer as ``"primary"``
            — a bare name broadcasts/sets the whole variable, ``NAME_<slot>``
            (1-based) writes one element of an array-valued variable (e.g.
            ``SPORC_1``/``SPORC_2`` for its two ``nactbioms`` slots). Kept as a
            distinct surface name (rather than silently reusing ``"primary"``)
            because the two are semantically different files, even though the
            write mechanics happen to coincide.
        Any other ``surface`` raises.
        """
        if surface == "secondary":
            self._write_pft_mgmt_surface(base_param_file, modifications, output_path)
            return
        if surface not in ("primary", "tertiary"):
            raise ValueError(
                f"EcoSIM parameter surfaces are 'primary' | 'secondary' | 'tertiary', got '{surface}'"
            )
        import netCDF4 as nc

        base_param_file = Path(base_param_file)
        output_path = Path(output_path)
        if base_param_file.suffix.lower() != ".nc":
            raise ValueError(
                f"EcoSIM write_parameter_file expects a .nc PFT file, got "
                f"{base_param_file.suffix} ({base_param_file}). JSON/CDL paths "
                "are a follow-up."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base_param_file, output_path)

        # Group per-PFT edits by variable: {varname: {pft_index0: value}}
        per_pft: Dict[str, Dict[int, float]] = {}
        whole: Dict[str, Any] = {}
        for key, val in modifications.items():
            m = _MOD_PFT_RE.match(key)
            if m and m.group("name") not in modifications:
                per_pft.setdefault(m.group("name"), {})[int(m.group("pft")) - 1] = val
            else:
                whole[key] = val

        ds = nc.Dataset(output_path, "a")
        try:
            allvars = set(ds.variables)
            for name, val in whole.items():
                if name not in allvars:
                    raise KeyError(f"parameter '{name}' not in {base_param_file.name}")
                var = ds.variables[name]
                if isinstance(val, (list, tuple)):
                    var[:] = val
                else:
                    var[:] = val  # broadcast scalar to the whole (per-PFT) array
            for name, pmap in per_pft.items():
                if name not in allvars:
                    raise KeyError(f"parameter '{name}' not in {base_param_file.name}")
                var = ds.variables[name]
                arr = var[:]
                for idx0, v in pmap.items():
                    if idx0 < 0 or idx0 >= arr.shape[0]:
                        raise IndexError(
                            f"{name}: PFT index {idx0 + 1} out of range "
                            f"(1..{arr.shape[0]})"
                        )
                    arr[idx0] = v
                var[:] = arr
        finally:
            ds.close()

    def _write_pft_mgmt_surface(
        self,
        base_mgmt_file: Path,
        modifications: Dict[str, Any],
        output_path: Path,
    ) -> None:
        """Write the SECONDARY surface: copy the pft_mgmt NetCDF and edit the
        `pft_pltinfo` string tokens (currently PPI = planting density).

        PPI is the 2nd whitespace token of '01049999 <PPI> 0.005', applied to the
        calibrated PFT slot across every year, written as an integer and
        SPACE-padded to the string width (null padding breaks the Fortran
        list-parse — the cycle-8 density footgun). Raises on an unknown token.
        """
        import netCDF4 as nc
        import numpy as np

        base = Path(base_mgmt_file)
        out = Path(output_path)
        if base.suffix.lower() != ".nc":
            raise ValueError(
                f"EcoSIM secondary surface expects the pft_mgmt .nc, got {base.suffix} ({base})"
            )
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base, out)

        ds = nc.Dataset(out, "r+")
        try:
            if _PFT_MGMT_VAR not in ds.variables:
                raise KeyError(
                    f"'{_PFT_MGMT_VAR}' not in {base.name} — not an EcoSIM pft_mgmt file?"
                )
            pi = ds.variables[_PFT_MGMT_VAR]           # (year, ntopou, maxpfts, string128)
            width = pi.shape[3]
            for name, val in modifications.items():
                # Accept a CANONICAL id (`PPI_1`) as well as a bare name (`PPI`). The ensemble
                # materializer keys every surface's edits by canonical id, so requiring bare names
                # here would make the secondary surface the one that could not be sampled through
                # the generic pipeline -- which is exactly the gap this accepts to close. The
                # trailing `_<axis>` is dropped rather than validated: this file writes the
                # calibrated PFT slot (`_PFT_MGMT_SLOT`) regardless of which axis id the list
                # declares, so honouring the suffix would imply a per-axis write that does not
                # happen.
                bare = name.rsplit("_", 1)[0] if name.rsplit("_", 1)[0] in _PFT_MGMT_TOKENS else name
                if bare not in _PFT_MGMT_TOKENS:
                    raise KeyError(
                        f"secondary-surface parameter '{name}' unknown "
                        f"(known: {sorted(_PFT_MGMT_TOKENS)})"
                    )
                tok = _PFT_MGMT_TOKENS[bare]
                token_str = (
                    str(int(round(float(val)))) if bare in _PFT_MGMT_INT else repr(float(val))
                )
                for y in range(pi.shape[0]):
                    s = pi[y, 0, _PFT_MGMT_SLOT].tobytes().decode("ascii", "replace")
                    s = s.strip("\x00").strip()
                    if not s:
                        continue
                    parts = s.split()
                    if len(parts) <= tok:
                        continue
                    parts[tok] = token_str
                    new = " ".join(parts)
                    buf = np.full(width, b" ", dtype="S1")   # SPACE pad, not null
                    for i, ch in enumerate(new[:width]):
                        buf[i] = ch.encode("ascii")
                    pi[y, 0, _PFT_MGMT_SLOT, :] = buf
            ds.sync()
        finally:
            ds.close()

    # ---- Case creation and submission ----

    def create_case(
        self,
        case_name: str,
        param_file: Path,
        config: Dict[str, Any],
        secondary_param_file: Optional[Path] = None,
        tertiary_param_file: Optional[Path] = None,
    ) -> Path:
        """Create a standalone-run case dir: staged namelist + rendered submit script.

        Returns the case directory path. Renders the runtemplate placeholders from
        ``config``; stages the base namelist into the case dir (repointed at
        ``param_file`` and the case output dir if a base namelist is provided).
        ``secondary_param_file`` (the pft_mgmt surface), if given, is staged and the
        ``spec.secondary_namelist_var`` line (``pft_mgmt_in``) repointed at it.
        ``tertiary_param_file`` (the MicrobePars surface), if given, is staged and
        the ``spec.tertiary_namelist_var`` line (``micpar_file_in``) repointed at
        it the same way.
        """
        out_root = Path(config.get("A2MC_OUTPUT_DIR") or (Path.cwd() / "ecosim_runs"))
        case_dir = out_root / case_name
        case_dir.mkdir(parents=True, exist_ok=True)

        # Stage the PFT param file into the case dir so the run is self-contained.
        staged_param = case_dir / Path(param_file).name
        if Path(param_file).resolve() != staged_param.resolve():
            shutil.copy2(param_file, staged_param)

        # Stage the SECONDARY surface file (e.g. per-case pft_mgmt with its PPI).
        staged_secondary = None
        if secondary_param_file is not None:
            staged_secondary = case_dir / Path(secondary_param_file).name
            if Path(secondary_param_file).resolve() != staged_secondary.resolve():
                shutil.copy2(secondary_param_file, staged_secondary)

        # Stage the TERTIARY surface file (e.g. per-case MicrobePars with soil-BGC rates).
        staged_tertiary = None
        if tertiary_param_file is not None:
            staged_tertiary = case_dir / Path(tertiary_param_file).name
            if Path(tertiary_param_file).resolve() != staged_tertiary.resolve():
                shutil.copy2(tertiary_param_file, staged_tertiary)

        # Stage + repoint the namelist if provided.
        runfile = case_dir / "runfile.nml"
        base_nml = config.get("A2MC_ECOSIM_BASE_NAMELIST")
        if base_nml and Path(base_nml).exists():
            text = Path(base_nml).read_text()
            # Repoint any pft-input path at our staged copy (best-effort, by basename).
            text = re.sub(
                r'(["\'])[^"\']*' + re.escape(Path(param_file).name) + r'\1',
                r'\1' + str(staged_param) + r'\1',
                text,
            )
            # Repoint the SECONDARY surface namelist var (spec-declared) at its staged copy.
            if staged_secondary is not None and self.spec.secondary_namelist_var:
                var = re.escape(self.spec.secondary_namelist_var)
                text, n = re.subn(
                    r'(' + var + r'\s*=\s*(["\']))[^"\']*(["\'])',
                    r'\1' + str(staged_secondary) + r'\3',
                    text,
                )
                if n == 0:
                    raise KeyError(
                        f"secondary_param_file given but '{self.spec.secondary_namelist_var}' "
                        f"not found in the base namelist to repoint"
                    )
            # Repoint the TERTIARY surface namelist var (spec-declared) at its staged copy.
            if staged_tertiary is not None and self.spec.tertiary_namelist_var:
                var = re.escape(self.spec.tertiary_namelist_var)
                text, n = re.subn(
                    r'(' + var + r'\s*=\s*(["\']))[^"\']*(["\'])',
                    r'\1' + str(staged_tertiary) + r'\3',
                    text,
                )
                if n == 0:
                    raise KeyError(
                        f"tertiary_param_file given but '{self.spec.tertiary_namelist_var}' "
                        f"not found in the base namelist to repoint"
                    )
            text = self._ensure_output_activation(text)
            nbytes = len(text.encode("utf-8"))
            if nbytes >= self._NAMELIST_BUFFER_BYTES:
                raise ValueError(
                    f"runfile.nml for case {case_name!r} would be {nbytes} bytes, at or over "
                    f"EcoSIM's fixed {self._NAMELIST_BUFFER_BYTES}-byte namelist read buffer "
                    f"(fileUtil.F90:25) -- the run would abort at startup with "
                    f"'namelist_to_buffer: IO ERROR reading namelist file into buffer: 0'. "
                    f"Trim comments in the base namelist ({base_nml}) or shorten staged paths."
                )
            runfile.write_text(text)
        else:
            # No base namelist supplied: leave a stub the site must fill.
            runfile.write_text(
                f"! EcoSIM runfile stub for {case_name}\n"
                f"! set forc_periods and point plant input at {staged_param}\n"
            )

        # Render the submit script from the runtemplate.
        # An explicit A2MC_ECOSIM_RUNTEMPLATE still wins; otherwise the default follows the
        # execution mode. The HPC template stays the default, so an unset A2MC_EXEC_MODE
        # behaves exactly as it always has.
        _default_tmpl = ("local_serial.sh.tmpl" if _exec_mode(config) == "local"
                         else "hpc_standalone.sh.tmpl")
        tmpl_path = Path(
            config.get("A2MC_ECOSIM_RUNTEMPLATE")
            or (Path(__file__).parent / "runtemplates" / _default_tmpl)
        )
        submit = case_dir / "submit.sh"
        if tmpl_path.exists():
            submit.write_text(self._render_template(tmpl_path.read_text(), case_name, case_dir, runfile, config))
            submit.chmod(0o755)
        return case_dir

    def _ensure_output_activation(self, text: str) -> str:
        """Ensure the inactive-by-default calibration outputs (``spec.hist_activate``)
        are in the namelist's ``hist_fincl1`` (the h0 tape field list).

        Idempotent: only adds vars not already requested; no-op if ``spec.hist_activate``
        is empty. EcoSIM registers 117/179 ``_pft`` outputs ``default='inactive'`` — they
        never reach the h0 tape unless named here (dev log 20260713c). This makes a staged
        case self-sufficient even if its base namelist omits the activation.
        """
        activate = getattr(self.spec, "hist_activate", ())
        if not activate:
            return text
        # existing hist_fincl1 field list (single- or multi-line continuation)
        m = re.search(r"hist_fincl1\s*=\s*[^\n]*(?:\n\s+'[^']*'[^\n]*)*", text)
        existing = set(re.findall(r"'([^']+)'", m.group(0))) if m else set()
        missing = [v for v in activate if v not in existing]
        if not missing:
            return text
        addition = ", ".join(f"'{v}'" for v in missing)
        if m:
            # prepend the missing vars right after `hist_fincl1 =` (valid Fortran list)
            return re.sub(r"(hist_fincl1\s*=\s*)", r"\g<1>" + addition + ", ", text, count=1)
        line = f"    hist_fincl1 = {addition}\n"
        if re.search(r"^\s*hist_fincl2\b", text, re.M):
            return re.sub(r"(^\s*hist_fincl2\b)", line + r"\1", text, count=1, flags=re.M)
        # fallback: insert before the first namelist terminator
        return re.sub(r"(\n/\n)", "\n" + line + r"/\n", text, count=1)

    def _render_template(self, tmpl: str, case_name: str, case_dir: Path, runfile: Path, config: Dict[str, Any]) -> str:
        subs = {
            "CASE_NAME": case_name,
            "ACCOUNT": config.get("A2MC_HPC_ACCOUNT", "m5199"),
            "QUEUE": config.get("A2MC_HPC_QUEUE", "shared"),
            "NODES": config.get("A2MC_HPC_NODES", "1"),
            "MPI_RANKS": config.get("A2MC_HPC_MPI_RANKS", "1"),
            "CPUS_PER_TASK": config.get("A2MC_HPC_CPUS_PER_TASK", "4"),
            "WALLTIME": config.get("A2MC_HPC_WALLTIME", "02:00:00"),
            "OUTPUT_DIR": str(case_dir),
            "OMP_NUM_THREADS": config.get("A2MC_OMP_NUM_THREADS", "1"),
            "MODEL_BINARY": config.get("A2MC_ECOSIM_BINARY", "ecosim.f90.x"),
            "RUN_CMD": str(runfile),
            "MODULES": config.get("A2MC_ECOSIM_MODULES", "# no module load required at runtime"),
            "PRE_RUN_HOOK": config.get("A2MC_ECOSIM_PRE_RUN_HOOK", "# (none)"),
            "POST_RUN_HOOK": config.get("A2MC_ECOSIM_POST_RUN_HOOK", "# (none)"),
        }
        out = tmpl
        for k, v in subs.items():
            out = out.replace("{{" + k + "}}", str(v))
        return out

    def submit_ensemble(
        self,
        case_paths: List[Path],
        config: Dict[str, Any],
    ) -> List[str]:
        """sbatch each case's submit.sh. Dry-run returns synthetic DRYRUN-* ids."""
        mode = _exec_mode(config)
        dry = _truthy(config.get("A2MC_DRY_RUN", ""))

        # An ABSENT sbatch used to fall through to a silent dry run: every case staged,
        # nothing launched, a synthetic id written to job_id.txt, and no warning. On a
        # workstation that is indistinguishable from a successful submission, and a monitor
        # armed on it waits forever for jobs that never existed. HPC behaviour is unchanged
        # -- where sbatch exists this branch is never reached.
        if mode == "hpc" and not dry and not shutil.which("sbatch"):
            raise RuntimeError(
                "no `sbatch` on PATH, so the HPC submit path cannot run.\n"
                "  To run on this machine instead:  export A2MC_EXEC_MODE=local\n"
                "  To stage without running:        export A2MC_DRY_RUN=1\n"
                "Refusing rather than silently staging: a dry run writes plausible job ids "
                "and launches nothing, which reads exactly like success.")

        if mode == "local" and not dry:
            for cp in case_paths:
                if not (Path(cp) / "submit.sh").exists():
                    raise FileNotFoundError(f"no submit.sh in case {cp}")
            workers = _local_workers(config)
            root = Path(case_paths[0]).resolve().parent if case_paths else Path.cwd()
            pid = _dispatch_local(case_paths, workers, root)
            job_ids = []
            for i, cp in enumerate(case_paths):
                jid = f"LOCAL-{pid}-{i:04d}"
                (Path(cp) / "job_id.txt").write_text(jid + "\n")
                job_ids.append(jid)
            return job_ids

        job_ids: List[str] = []
        for i, cp in enumerate(case_paths):
            submit = Path(cp) / "submit.sh"
            if not submit.exists():
                raise FileNotFoundError(f"no submit.sh in case {cp}")
            if dry:
                jid = f"DRYRUN-{i:04d}"
            else:
                res = subprocess.run(
                    ["sbatch", "--parsable", str(submit)],
                    cwd=str(cp), capture_output=True, text=True,
                )
                if res.returncode != 0:
                    raise RuntimeError(f"sbatch failed for {cp}: {res.stderr.strip()}")
                jid = res.stdout.strip().split(";")[0]
            (Path(cp) / "job_id.txt").write_text(jid + "\n")
            job_ids.append(jid)
        return job_ids

    def expected_final_restart_year(self, case_path: Path):
        """The calendar year of the restart a COMPLETE run writes, or None if undeterminable.

        EcoSIM writes a restart set stamped `<final_year + 1>-01-01` after finishing its last
        simulated year, so the expected stamp is `start_date`'s year plus the total number of
        simulated years. `forc_periods` is a sequence of `(y0, y1, repeats)` triplets and a
        spin-up recycles forcing by repeating a triplet, so the total is the SUM of
        `(y1 - y0 + 1) * repeats`, not simply `y1 - y0 + 1`.

        Read from the case's OWN runfile.nml, so a case whose run length was edited (the smoke
        ensemble shortens it) is judged against its own configuration rather than a global
        assumption.
        """
        nml = Path(case_path) / "runfile.nml"
        if not nml.is_file():
            return None
        try:
            txt = nml.read_text(errors="ignore")
        except OSError:
            return None
        m_start = re.search(r"start_date\s*=\s*'(\d{4})", txt)
        m_fp = re.search(r"forc_periods\s*=\s*([0-9,\s]+)", txt)
        if not m_start or not m_fp:
            return None
        nums = [int(x) for x in re.findall(r"\d+", m_fp.group(1))]
        if not nums or len(nums) % 3 != 0:
            return None
        total = 0
        for i in range(0, len(nums), 3):
            y0, y1, repeats = nums[i], nums[i + 1], nums[i + 2]
            if y1 < y0 or repeats < 1:
                return None
            total += (y1 - y0 + 1) * repeats
        return int(m_start.group(1)) + total

    def check_case_status(self, case_path: Path) -> str:
        """'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'UNKNOWN'.

        COMPLETED requires the FINAL RESTART, not the presence of an output tape. EcoSIM creates
        its single `h0` tape at initialisation and appends to it, so "the tape exists" means the
        run STARTED. Worse, a run killed at the wall clock or dying mid-way also leaves that tape,
        which made a truncated run indistinguishable from a complete one -- the exact failure mode
        an ensemble must detect. Measured 2026-08-20 on R3 chunk 1: the tape test reported 32
        COMPLETED where sacct had 12 terminal tasks.

        The restart stamped `<final year + 1>-01-01` is written only after the last simulated year
        finishes, so its presence is positive evidence of a complete run.
        """
        cp = Path(case_path)
        final_year = self.expected_final_restart_year(cp)
        if final_year is not None and list(cp.glob(f"*.ecosim.r.{final_year}-*.nc")):
            return "COMPLETED"
        errs = list(cp.glob("slurm_*.err"))
        for e in errs:
            try:
                txt = e.read_text(errors="ignore")
            except OSError:
                continue
            if re.search(r"ERROR|FAILED|srun: error|Killed|OOM", txt):
                return "FAILED"
        if list(cp.glob("slurm_*.out")) or list(cp.glob("*.ecosim.h*.nc")):
            # Started but no final restart: still running, or died part-way. The two are not
            # separable from inside the case dir -- model_ensemble_status reconciles this against
            # the scheduler, where a terminal slurm state plus a non-COMPLETED model check is
            # correctly reported FAILED.
            return "RUNNING"
        if final_year is None:
            # No runfile.nml to read a run length from, so completion cannot be asserted. Saying
            # COMPLETED here is what the old tape test effectively did; UNKNOWN is the honest
            # answer and keeps screen_ensemble (which skips anything != COMPLETED) on the safe side.
            return "UNKNOWN"
        return "PENDING"

    # ---- Output extraction (real; reads the h0 tape) ----

    def extract_history_variables(
        self,
        case_path: Path,
        variables: List[str],
        time_range: Optional[tuple] = None,
        tape: str = "h0",
    ) -> Any:
        """Extract variables from one of the case's history tapes (default ``h0``, daily).

        ``tape`` selects which ``hist_fincl<N>``/``hist_nhtfrq`` tape to read (e.g. ``h1`` for
        an hourly second tape, wired for R3 -- see ``case_template/run_r3_hourly.nml``,
        ``memory/logs/20260809e_*.md``). Concatenates EVERY file matching
        ``*.ecosim.{tape}.*.nc`` in filename-sorted (== chronological; tape filenames carry a
        date stamp) order along the time axis. This matters once a tape rolls over multiple
        files -- ``hist_mfilt`` (36500) covers the whole ~8401-record daily tape in one file,
        but an hourly tape for the same run is ~24x more records and DOES roll over into
        several per-case files; reading only the first file (the pre-R3 behavior) would
        silently drop most of the run.

        Returns a dict ``{var_name: numpy.ndarray}`` (plus ``time`` if present).
        ``time_range`` is an inclusive (start, end) pair of 0-based indices into the
        CONCATENATED series. Raises if no tape file or a requested variable is missing.
        """
        import netCDF4 as nc
        import numpy as np

        cp = Path(case_path)
        tapes = sorted(cp.glob(f"*.ecosim.{tape}.*.nc"))
        if not tapes:
            raise FileNotFoundError(f"no *.ecosim.{tape}.*.nc tape in {cp}")

        per_file: Dict[str, List[Any]] = {v: [] for v in variables}
        time_chunks: List[Any] = []
        have_time = False
        for i, tp in enumerate(tapes):
            ds = nc.Dataset(tp, "r")
            try:
                if i == 0:
                    missing = [v for v in variables if v not in ds.variables]
                    if missing:
                        raise KeyError(f"variables not on tape {tp.name}: {missing}")
                    have_time = "time" in ds.variables
                for v in variables:
                    per_file[v].append(np.asarray(ds.variables[v][:]))
                if have_time:
                    time_chunks.append(np.asarray(ds.variables["time"][:]))
            finally:
                ds.close()

        out: Dict[str, Any] = {
            v: (np.concatenate(chunks, axis=0) if len(chunks) > 1 else chunks[0])
            for v, chunks in per_file.items()
        }
        if have_time:
            out["time"] = np.concatenate(time_chunks) if len(time_chunks) > 1 else time_chunks[0]

        if time_range is not None:
            lo, hi = time_range
            out = {k: v[lo:hi + 1] for k, v in out.items()}
        return out

    def reduce_ecosystem(self, extracted: Dict[str, Any],
                         target: Dict[str, Any], how: str) -> float:
        """EcoSIM plot-scale target reductions (overrides base.reduce_ecosystem).

        EcoSIM-specific assumptions: FLAT per-PFT axis ``(time, pft)``; a DAILY tape on a
        REAL Gregorian calendar (366 records in a leap year — see ``_year_blocks``, NOT the
        no-leap 365 that ELM uses); per-PFT rate in gC/m2/hr (integrate ×24 h/day); spval
        fill 1e+30. ``how`` ∈ ``model_evaluate_case.ECOSYSTEM_REDUCES``.
        """
        import numpy as np
        SPVAL = 1.0e29

        def mask(a):
            a = np.asarray(a, dtype=float)
            return np.where(np.abs(a) > SPVAL, np.nan, a)

        # NOTE: the former `win(series)` helper was REMOVED (2026-08-07). It sliced
        # `target["window"]` as raw record indices, and its only consumer was
        # `growing_season_mean_abs`. Because `window` is written as a YEAR range everywhere in
        # targets.yaml (Fs had [4380, 8395] = 12*365 to 23*365), that reducer returned an
        # ALL-DAYS mean of eleven years against an observation defined as a May-Sep mean --
        # understating Fs by 1.74x, measured across the six R2 c04 runs. It is deleted rather
        # than fixed so nothing reaches for it again; season selection now happens by calendar
        # month below. Full account: use_cases/EcoSIM_BioCON/memory/logs/20260807b_*.md

        def _year_blocks(n):
            """Record-index slices for each COMPLETE calendar year in a daily tape.

            Returns ``[(year, lo, hi), ...]`` (``hi`` exclusive), or ``None`` when the run's
            start year is unknown and we must fall back to fixed 365-record blocking.

            EcoSIM advances a REAL Gregorian calendar — `ecosim_time_mod.F90` sets
            `leap_yr = isLeapi(year0)` (:181), steps `doy = mod(doy, 365+leap_yr)` (:468) and
            returns `get_days_cur_year = 366` on leap years (:657-658); there is NO no-leap
            switch in the `&ecosim_time` namelist. So a daily tape has 366 records in a leap
            year: BioCON 2000-2022 is 8401 records, not 23*365 = 8395. Fixed-365 blocking
            slipped up to 6 days across that run and dropped its final 6 records.
            (`get_days_per_year()` :648 hardwires 365 but is DEAD CODE — no caller. Do not
            cite it as evidence of a no-leap calendar.)
            """
            sy = target.get("start_year")
            if sy is None:
                sy = os.environ.get("A2MC_VALIDATION_START_YEAR")
            if sy in (None, ""):
                warnings.warn(
                    "EcoSIM year-blocking fell back to a fixed 365 records/year: no start year "
                    "(target 'start_year' or $A2MC_VALIDATION_START_YEAR). EcoSIM uses a REAL leap "
                    "calendar, so year blocks will slip a day per leap year. Set the start year.",
                    RuntimeWarning, stacklevel=2)
                return None
            # The blocking itself lives in `tools.calendar_blocks.year_blocks`, shared with
            # `scripts/extract_and_plot_adapter_ensemble.py`. Consolidated 2026-08-16: this logic
            # existed in three places and the ensemble driver's copy was WRONG (`n // 365`), which
            # is exactly what an unimportable nested copy invites. Resolving the start year stays
            # here because it is A2MC config plumbing, not calendar arithmetic.
            #
            # `year_blocks` uses `calendar.isleap`, which is equivalent to the Gregorian rule this
            # function spelled out by hand; `tests/test_calendar_blocks.py` asserts the two agree
            # across 1800-2400 rather than leaving it to inspection.
            from tools.calendar_blocks import year_blocks
            return year_blocks(n, int(sy))

        def _select_years(per_year, blocks, what):
            """Pick the scored years: prefer explicit `window_years` (absolute calendar years),
            else fall back to the legacy timestep `window` reading (index // 365)."""
            wy = target.get("window_years")
            if wy:
                y0, y1 = wy
                have = {y for (y, _, _) in blocks}
                keep = [v for (y, _, _), v in zip(blocks, per_year) if y0 <= y <= y1]
                if not keep:
                    raise ValueError(f"{what}: window_years {wy} selects no complete year "
                                     f"(tape covers {blocks[0][0]}-{blocks[-1][0]})")
                # PARTIAL coverage is an error too, not just empty coverage. A mean over part
                # of the window is a different statistic, and the part that goes missing is
                # never random: a run that terminates early terminates BECAUSE it went unstable,
                # so the surviving tail is exactly where the values blow up.
                #
                # Observed 2026-08-15 in the R3 c00 probe. Of 258 corners, 9 ended early. Seven
                # died before 2012 and errored cleanly here. The other two reached PART of the
                # 2012-2022 window and were scored without complaint: case 56 (through 2015)
                # returned Fs 268.9 and case 63 (through 2018) returned Fs 275.5, against a
                # normal range of roughly 0.1-8. sacct reported all 258 COMPLETED, so nothing
                # upstream flagged them. GATE_MONOTONE then took case 63 as the ensemble maximum
                # and failed, which read as "the corner design does not bound the envelope" when
                # the truth was "two rows are garbage".
                missing = sorted(y for y in range(y0, y1 + 1) if y not in have)
                if missing:
                    raise ValueError(
                        f"{what}: window_years {wy} is only partially covered — missing complete "
                        f"year(s) {missing} (tape covers {min(have)}-{max(have)}). A mean over a "
                        f"truncated window is a different statistic; an early-terminating run's "
                        f"surviving tail is biased toward the instability that killed it.")
                return np.array(keep)
            if target.get("window"):
                lo, hi = target["window"]
                lo //= 365
                hi = (len(per_year) * 365 - 1 if hi == -1 else hi) // 365
                sel = per_year[lo:hi + 1]
                if len(sel) == 0:
                    # The window_years branch above already raised on an empty selection; this
                    # one used to slice to empty and hand nanmean an empty array, scoring the
                    # target as NaN. A silently missing target is worse than a loud failure.
                    raise ValueError(
                        f"{what}: legacy window {target['window']} (read as years "
                        f"{lo}-{hi}) selects no complete year from {len(per_year)} available")
                return sel
            return per_year

        var = target["variable"]
        vlist = list(var) if isinstance(var, (list, tuple)) else [var]

        if how == "sum_pft_peak":
            # Σ over PFTs of one-or-more per-PFT vars → the PER-YEAR peak, then MEAN over the
            # window YEARS. The obs is "peak standing biomass, control MEAN 2012-2022" = a year-mean
            # of annual (August) peaks, NOT a single window maximum (which over-scores any config with
            # -- the "(August)" is the MANUSCRIPT's, verified verbatim 2026-09-05: biomass was
            # "sampled annually at peak standing biomass (in August)". It was uncited here until
            # then, and this comment quoting targets.yaml's description, which quoted nobody, was a
            # circular justification for a reducer whose choice moves plant_C by 1.6x-2.4x --
            # a transient spike — a latent bug that only showed once a peaky config was scored, since a
            # flat reference has max ≈ mean; verified on D4: mean-of-annual-peaks 595.7 == R1's 596,
            # vs the old window-max 813). `window` here is a YEAR range [lo, hi] (like `annual`).
            total = None
            for v in vlist:
                a = mask(extracted[v])
                if a.ndim < 2:
                    raise ValueError(f"sum_pft_peak expects (time, pft), got {v} ndim={a.ndim}")
                per_t = np.nansum(a, axis=1)          # EcoSIM flat PFT axis
                total = per_t if total is None else total + per_t
            n = len(total)
            blocks = _year_blocks(n)
            if blocks is not None:                               # real calendar years (leap-aware)
                yr_peak = np.array([np.nanmax(total[lo:hi]) for _, lo, hi in blocks])
                yr_peak = _select_years(yr_peak, blocks, "sum_pft_peak")
            else:                                    # fallback: fixed 365-record blocks
                yrs = n // 365
                if yrs < 1:
                    raise ValueError(f"sum_pft_peak needs >=1 full year (365 recs); got {n} recs")
                yr_peak = np.array([np.nanmax(total[y * 365:(y + 1) * 365]) for y in range(yrs)])
                yr_peak = _select_years(yr_peak, None, "sum_pft_peak")
            if len(yr_peak) < 1:
                raise ValueError(f"sum_pft_peak needs >=1 full year (365 recs); got {n} recs")
            return float(np.nanmean(yr_peak))

        if how == "growing_season_mean_abs":
            # |column series| (soil CO2 flux Fs is <0 into atmosphere), meaned over the SEASON
            # within each scored year, then over years -- a mean of per-year growing-season
            # means, which is what a "growing-season mean, control mean 2012-2022" observation
            # is. Season months come from `season_months` (default May-Sep) and are resolved to
            # day-of-year PER YEAR, so a leap year shifts them correctly; years come from
            # `window_years`, the same field every other reducer uses.
            series = np.asarray(self.select_group_series(mask(extracted[vlist[0]]), target))
            a = np.abs(series)
            m0, m1 = target.get("season_months", [5, 9])
            blocks = _year_blocks(len(a))
            if blocks is not None:
                per_year = []
                for (y, lo, hi) in blocks:
                    d0 = _dt.date(y, m0, 1).timetuple().tm_yday - 1          # inclusive
                    d1 = _dt.date(y, m1, calendar.monthrange(y, m1)[1]).timetuple().tm_yday
                    seg = a[lo + d0: lo + d1]                                 # d1 exclusive
                    if seg.size == 0:
                        raise ValueError(
                            f"growing_season_mean_abs: season months {[m0, m1]} select no "
                            f"records in year {y}")
                    per_year.append(np.nanmean(seg))
                per_year = _select_years(np.array(per_year), blocks,
                                         "growing_season_mean_abs")
                return float(np.nanmean(per_year))
            # No start year -> fixed 365-record blocking (the _year_blocks warning already
            # fired). Use fixed day-of-year bounds; this is R2's per-cycle convention and
            # drifts <=6 days by year 23, measured at 0.4% on Fs.
            n = len(a)
            yrs = n // 365
            if yrs < 1:
                raise ValueError(f"growing_season_mean_abs needs >=1 full year; got {n} recs")
            d0 = _dt.date(2001, m0, 1).timetuple().tm_yday - 1               # non-leap ref
            d1 = _dt.date(2001, m1, calendar.monthrange(2001, m1)[1]).timetuple().tm_yday
            per_year = np.array([np.nanmean(a[y * 365 + d0: y * 365 + d1]) for y in range(yrs)])
            return float(np.nanmean(_select_years(per_year, None, "growing_season_mean_abs")))

        if how == "growing_season_daytime_mean_abs":
            # Like `growing_season_mean_abs`, but ALSO restricted to a fixed hour-of-day
            # window -- e.g. Fs's observation is a DAYTIME-sampled mean, not an all-hours one
            # (memory/logs/20260809d_*.md, 20260809e_*.md). Reads whichever tape `target`
            # requested (`target["tape"]`, e.g. "h1"/hourly -- this reducer is meaningless on
            # the h0 daily tape, which has already averaged the diel cycle away). The actual
            # window+season selection is done by the model-agnostic
            # `tools.subdaily_window_reduce.growing_season_window_mean_abs` -- this method's
            # job is only to turn EcoSIM's own record index into (hour_of_day, month, year)
            # tags, via the SAME leap-aware calendar `_year_blocks` uses for the daily tape.
            #
            # `daytime_window_hours` is REQUIRED from `target` (no default here): it must be a
            # constant derived independently of the series being reduced -- a default baked
            # into this generic per-model reducer would either be wrong for a future site with
            # a different local-solar-noon offset, or silently encode this site's choice as if
            # it were a framework default. See the module docstring in subdaily_window_reduce.py.
            from tools.subdaily_window_reduce import growing_season_window_mean_abs

            window_hours = target.get("daytime_window_hours")
            if not window_hours:
                raise ValueError(
                    "growing_season_daytime_mean_abs requires target['daytime_window_hours'] "
                    "(e.g. [16,17,18,19,20,21] -- a fixed, forcing-derived constant; see "
                    "use_cases/EcoSIM_BioCON/memory/logs/20260809d_*.md for how BioCON's "
                    "was chosen). Not defaulted here -- it must not silently vary by site.")

            series = np.abs(np.asarray(self.select_group_series(mask(extracted[vlist[0]]), target)))
            n = len(series)
            if n % 24 != 0:
                raise ValueError(
                    f"growing_season_daytime_mean_abs expects an hourly tape (24 "
                    f"records/day); got {n} records, not a multiple of 24 -- check "
                    f"target['tape'] points at the hourly tape (e.g. 'h1'), not 'h0'.")
            day_blocks = _year_blocks(n // 24)
            if day_blocks is None:
                raise ValueError(
                    "growing_season_daytime_mean_abs needs a start year (target 'start_year' "
                    "or $A2MC_VALIDATION_START_YEAR) -- EcoSIM's real leap calendar cannot be "
                    "safely fixed-blocked at hourly resolution.")
            year_arr = np.empty(n, dtype=int)
            month_arr = np.empty(n, dtype=int)
            for (y, lo_day, hi_day) in day_blocks:
                cum = np.cumsum([0] + [calendar.monthrange(y, m)[1] for m in range(1, 13)])
                month_per_day = np.searchsorted(cum, np.arange(hi_day - lo_day), side="right")
                year_arr[lo_day * 24: hi_day * 24] = y
                month_arr[lo_day * 24: hi_day * 24] = np.repeat(month_per_day, 24)
            hour_arr = np.arange(n) % 24

            m0, m1 = target.get("season_months", [5, 9])
            wy = target.get("window_years")
            return growing_season_window_mean_abs(
                series, hour_arr, month_arr, year_arr,
                window_hours=window_hours, season_months=(m0, m1),
                window_years=tuple(wy) if wy else None,
            )

        if how == "annual":
            # Integrate the per-PFT RATE (gC/m2/hr) over each REAL calendar year, Σ PFTs.
            # Leap-aware via `_year_blocks` (EcoSIM runs a true Gregorian calendar — see there).
            # NB: do NOT diff the "cumulative" ECO_NPP_col — its year-boundary diffs are not
            # the annual flux (fluctuate ±180); NPP_pft integration matches obs. See 20260715c.
            a = mask(extracted[vlist[0]])
            rate = np.nansum(a, axis=1) if a.ndim >= 2 else a
            n = rate.shape[0]
            step_h = float(target.get("step_hours", 24))
            blocks = _year_blocks(n)
            if blocks is not None:                            # real calendar years (leap-aware)
                annual = np.array([np.nansum(rate[lo:hi]) * step_h for _, lo, hi in blocks])
                annual = _select_years(annual, blocks, "annual")
            else:                                 # fallback: fixed 365-record blocks
                yrs = n // 365
                if yrs < 1:
                    raise ValueError(f"annual reduce needs >=1 full year (365 recs); got {n} recs")
                annual = np.array([np.nansum(rate[y * 365:(y + 1) * 365]) * step_h for y in range(yrs)])
                annual = _select_years(annual, None, "annual")
            if len(annual) < 1:
                raise ValueError(f"annual reduce needs >=1 full year (365 recs); got {n} recs")
            return float(np.nanmean(annual))

        if how == "year_end":
            # Annual total of a WITHIN-YEAR CUMULATIVE = the LAST record of each calendar year.
            #
            # Several EcoSIM outputs are cumulatives that reset each 1 January, and the registry
            # says so itself: `ECO_GPP_col` long_name "cumulative ecosystem GPP", `ECO_ET_col`
            # "cumulative total evapotranspiration", `ECO_RA_col` "cumulative ecosystem
            # autotrophic respiration". The harvest pair (`HVST_C_FLX_pft` <-
            # EcoHavstElmnt_CumYr_pft, `ECO_HVST_C_col` <- ..._col) are the same shape while
            # being labelled `gC/m2/hr`, so the units string is NOT a reliable discriminator —
            # check the fill, or check whether the series resets each 1 January.
            #
            # `annual` is the WRONG reduce for these: it integrates a RATE (Σ over the year ×
            # step_hours) and would inflate a cumulative by ~24×365. Nothing raises; the score
            # is simply garbage. That is why this reduce exists.
            #
            # Σ over several variables happens BEFORE the year-end pick (Reco = RA + RH), and
            # `negate: true` flips the sign for variables stored as losses (RA/RH are negative
            # cumulatives; the observation is positive). Both are linear and pointwise, so the
            # order relative to the pick does not matter — done first for readability.
            total = None
            for v in vlist:
                a = mask(extracted[v])
                col = np.nansum(a, axis=1) if a.ndim >= 2 else a
                total = col if total is None else total + col
            if target.get("negate"):
                total = -total
            n = total.shape[0]
            blocks = _year_blocks(n)
            if blocks is not None:                            # real calendar years (leap-aware)
                if len(blocks) < 1:
                    raise ValueError(
                        f"year_end needs >=1 COMPLETE calendar year; got {n} records")
                per_year = np.array([total[hi - 1] for _, _, hi in blocks])
                per_year = _select_years(per_year, blocks, "year_end")
            else:                                 # fallback: fixed 365-record blocks
                yrs = n // 365
                if yrs < 1:
                    raise ValueError(
                        f"year_end needs >=1 full year (365 recs); got {n} recs")
                per_year = np.array([total[(y + 1) * 365 - 1] for y in range(yrs)])
                per_year = _select_years(per_year, None, "year_end")
            return float(np.nanmean(per_year))

        if how == "depth_integral":
            raise NotImplementedError(
                f"depth_integral not wired: {vlist[0]} is gC/m3 (vertically resolved); scoring it "
                f"needs the soil-layer thicknesses (absent from the h0 tape + grid input). See "
                f"use_cases/EcoSIM_BioCON/validation/targets.yaml EXTRACTION status #5.")

        raise ValueError(f"unknown ecosystem reduce '{how}'")

    def list_diagnostic_tools(self) -> List[Path]:
        # No EcoSIM-specific phase3 diagnostic scripts yet.
        return []
