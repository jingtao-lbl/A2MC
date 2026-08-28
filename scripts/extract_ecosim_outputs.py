#!/usr/bin/env python3
"""
extract_ecosim_outputs.py - Build ecosim_output_info_<commit>.cdl from a
sample EcoSIM history tape.

Two sources, one CDL shape (`rag/output_parser.py:FATESOutputParser`):

* ``--from-source <checkout>`` (AUTHORITATIVE, preferred) — scans every
  ``hist_addfld1d/2d`` call in the EcoSIM source (like `extract_elm_outputs.py`
  does for ELM). This is version-true: it lists exactly the fields the pinned
  binary defines, and tags each with a ``:status`` active/inactive attribute
  (117/179 _pft fields are ``default='inactive'`` and never hit the h0 tape
  unless named in ``hist_fincl1``).
* ``--output-nc <tape>`` (default, legacy) — reads a sample h0 tape header. A
  tape only reflects the vars ACTIVE in that one run and can be from a DIFFERENT
  binary version than the pinned commit (the BioCON reference tape carried 52
  phantom vars absent from 2dea74d9 and was missing 117 real fields — which is
  why the source mode was added, dev log 20260713e).

Why a CDL (not just the .nc)
----------------------------
The A2MC RAG/GraphRAG build (Step 2) and the validators (V1/V2) consume a
text CDL of the output surface, pinned to a source commit, so the output
inventory is diffable and version-associated. The 234 MB BioCON tape is
gitignored; this ~500-var CDL is the committed, source-pinned artifact.

Usage
-----
    python scripts/extract_ecosim_outputs.py \\
        --output-nc Offline/EcoSIM_sample_files/output/BioCON__test1_ex1.ecosim.h0.2000-01-01-00000.nc \\
        --output docs/ecosim-knowledge-base/ecosim_output_info_2dea74d9.cdl \\
        --commit 2dea74d9

Requires netCDF4 (present in the Python 3.10 framework build, not in a2mc_env).

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List


# NetCDF numeric dtype kind -> CDL type token. FATESOutputParser only
# recognizes float/double/int in its variable-declaration regex, so map
# everything numeric onto those three and skip pure-string metadata vars.
def _cdl_type(dtype_str: str) -> str:
    d = dtype_str.lower()
    if "float64" in d or d == "double":
        return "double"
    if "float" in d:
        return "float"
    if "int" in d:
        return "int"
    # char/string/object -> not a calibration output; caller skips these
    return ""


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def extract(output_nc: Path) -> Dict:
    try:
        import netCDF4 as nclib
    except ImportError:
        raise ImportError(
            "netCDF4 required. Use the Python 3.10 framework build "
            "(/Library/Frameworks/Python.framework/Versions/3.10/bin/python3), "
            "not a2mc_env."
        )
    ds = nclib.Dataset(output_nc, "r")
    dims = {name: (len(dim), dim.isunlimited()) for name, dim in ds.dimensions.items()}
    variables: List[Dict] = []
    skipped_nonnumeric = 0
    for name, var in ds.variables.items():
        ctype = _cdl_type(str(var.dtype))
        if not ctype:
            skipped_nonnumeric += 1
            continue
        variables.append({
            "name": name,
            "type": ctype,
            "dimensions": list(var.dimensions),
            "units": getattr(var, "units", ""),
            "long_name": getattr(var, "long_name", ""),
            "cell_methods": getattr(var, "cell_methods", ""),
        })
    ds.close()
    return {"dims": dims, "variables": variables, "skipped": skipped_nonnumeric}


def extract_from_source(checkout: Path) -> Dict:
    """Build the output registry from the model SOURCE — authoritative for a
    version-pinned commit.

    A history TAPE only reflects the vars ACTIVE in the run that produced it, and
    can be from a DIFFERENT binary version than the pinned commit (we found the
    BioCON reference tape carried 52 phantom vars absent from 2dea74d9 and was
    missing 117 real fields). The source ``hist_addfld1d/2d`` registry is the
    ground truth: every field the binary defines, with units, long_name, primary
    axis, and the ``default='inactive'`` flag (117/179 _pft fields are inactive —
    they never reach the h0 tape unless named in ``hist_fincl1``). Returns the same
    shape as :func:`extract` plus a per-var ``status`` ('active'|'inactive').
    """
    import glob
    import re

    ptr_axis = {"ptr_patch": "pft", "ptr_col": "column",
                "ptr_gcell": "gridcell", "ptr_topo": "topounit"}
    text = ""
    for f in glob.glob(str(checkout / "f90src" / "**" / "*.F90"), recursive=True):
        try:
            text += Path(f).read_text(errors="ignore")
        except OSError:
            pass

    variables: List[Dict] = []
    dims_used = {"time"}
    seen = set()
    for ndim, body in re.findall(r"hist_addfld([12])d\((.*?)\)", text, re.S):
        m = re.search(r"fname\s*=\s*'([^']+)'", body)
        if not m or m.group(1) in seen:
            continue
        name = m.group(1)
        seen.add(name)
        um = re.search(r"units\s*=\s*'([^']*)'", body)
        lm = re.search(r"long_name\s*=\s*'([^']*)'", body)
        status = "inactive" if "inactive" in body else "active"
        axis = next((a for p, a in ptr_axis.items() if p in body), None)
        if axis is None:  # 2d calls carry no ptr_*; fall back to the fname suffix
            axis = ("pft" if name.endswith("_pft")
                    else "column" if name.endswith(("_col", "_vr", "_litr", "_brch")) else "column")
        if ndim == "1":
            dimensions = ["time", axis]
        else:
            t2 = re.search(r"type2d\s*=\s*'([^']*)'", body)
            dimensions = ["time", t2.group(1) if t2 else "level", axis]
        dims_used.update(dimensions)
        variables.append({
            "name": name, "type": "float", "dimensions": dimensions,
            "units": um.group(1) if um else "", "long_name": lm.group(1) if lm else "",
            "cell_methods": "", "status": status,
        })
    # Registry is size-agnostic (per-case dim sizes vary); nominal 1 for the header.
    dims = {d: (0 if d == "time" else 1, d == "time") for d in dims_used}
    return {"dims": dims, "variables": variables, "skipped": 0}


def emit_cdl(parsed: Dict, out_path: Path, commit: str, source_nc: Path,
             source_checkout: Path = None) -> None:
    short = commit[:8] if len(commit) >= 8 else commit
    today = datetime.now().strftime("%Y-%m-%d")
    dims = parsed["dims"]
    variables = sorted(parsed["variables"], key=lambda v: v["name"])

    if source_checkout is not None:
        lines = [
            "// EcoSIM history-output variable registry",
            f"// Source pin: EcoSIM commit {short}",
            f"//             DERIVED FROM SOURCE — every hist_addfld1d/2d call in",
            f"//             {source_checkout}/f90src (the authoritative, version-true registry).",
            f"// Generated: {today}",
            "//",
            "// This is the ground truth for a version-pinned commit: a history TAPE only",
            "// reflects the vars ACTIVE in one run and can be from a different binary version.",
            "// Each var carries its source long_name, units, and a :status attribute —",
            "//   status=\"inactive\" means default='inactive' in HistDataType.F90: the field is",
            "//   NOT written to the h0 tape unless named in the hist_fincl1 namelist.",
            "// Dimension sizes are NOMINAL (=1; per-case sizes vary); the axis names are true.",
            "",
            f"netcdf ecosim_output_{short} {{",
            "  dimensions:",
        ]
    else:
        lines = [
            "// EcoSIM history-output variable registry",
            f"// Source pin: EcoSIM commit {short}",
            f"//             extracted from a sample h0 history tape's NetCDF header:",
            f"//             {source_nc.name}",
            f"// Generated: {today}",
            "//",
            "// Each variable's CDL attributes mirror what the EcoSIM history writer",
            "// stored on the tape: long_name, units, plus optional cell_methods.",
            "// Dimension sizes are this sample case's actual sizes (BioCON test1_ex1).",
            "// Pure-string/metadata variables (e.g. time_bounds indices) are omitted.",
            "",
            f"netcdf ecosim_output_{short} {{",
            "  dimensions:",
        ]
    # time first (unlimited), then the rest sorted
    if "time" in dims:
        size, _ = dims["time"]
        lines.append(f"    time = UNLIMITED ;   // ({size} currently)")
    for name in sorted(d for d in dims if d != "time"):
        size, unlimited = dims[name]
        if unlimited:
            lines.append(f"    {name} = UNLIMITED ;   // ({size} currently)")
        else:
            lines.append(f"    {name} = {size} ;")

    lines.append("  variables:")
    for v in variables:
        dstr = ", ".join(v["dimensions"])
        lines.append(f"    {v['type']} {v['name']}({dstr}) ;")
        # Indented `:attr = "..."` style — the form rag/output_parser.py:
        # FATESOutputParser recognizes (it does not parse the `varname:attr`
        # qualified form that raw `ncdump -h` emits).
        if v["long_name"]:
            lines.append(f"      :long_name = \"{_escape(v['long_name'])}\" ;")
        if v["units"]:
            lines.append(f"      :units = \"{_escape(v['units'])}\" ;")
        if v["cell_methods"]:
            lines.append(f"      :cell_methods = \"{_escape(v['cell_methods'])}\" ;")
        if v.get("status"):
            lines.append(f"      :status = \"{v['status']}\" ;")
    lines.append("}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Extract EcoSIM output registry to CDL")
    ap.add_argument(
        "--output-nc", type=Path,
        default=Path("Offline/EcoSIM_sample_files/output/"
                     "BioCON__test1_ex1.ecosim.h0.2000-01-01-00000.nc"),
        help="Path to a sample EcoSIM h0 history tape",
    )
    ap.add_argument(
        "--output", type=Path,
        default=Path("docs/ecosim-knowledge-base/ecosim_output_info_2dea74d9.cdl"),
        help="Output CDL path",
    )
    ap.add_argument(
        "--commit", default="2dea74d9",
        help="EcoSIM source commit for the source-pin header (default: 2dea74d9)",
    )
    ap.add_argument(
        "--from-source", type=Path, default=None, metavar="CHECKOUT",
        help="Build the registry from the model SOURCE tree (authoritative, version-true; "
             "adds a :status active/inactive attribute) instead of from a history tape. "
             "Point at the EcoSIM checkout root of the pinned commit.",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if args.from_source is not None:
        if not (args.from_source / "f90src").is_dir():
            print(f"ERROR: not an EcoSIM checkout (no f90src/): {args.from_source}", file=sys.stderr)
            return 1
        print(f"Scanning EcoSIM source registry: {args.from_source}/f90src")
        parsed = extract_from_source(args.from_source)
        n = len(parsed["variables"])
        nact = sum(1 for v in parsed["variables"] if v.get("status") == "active")
        print(f"  {n} registered output fields ({nact} active, {n - nact} inactive-by-default)")
        print(f"Writing {args.output}")
        emit_cdl(parsed, args.output, args.commit, args.output, source_checkout=args.from_source)
        print(f"Done. {n} variables written (source-derived).")
        return 0
    if not args.output_nc.exists():
        print(f"ERROR: sample output tape not found: {args.output_nc}", file=sys.stderr)
        return 1
    print(f"Reading EcoSIM history tape: {args.output_nc}")
    parsed = extract(args.output_nc)
    n = len(parsed["variables"])
    print(f"  {n} numeric output variables "
          f"({parsed['skipped']} non-numeric/metadata vars skipped)")
    print(f"  {len(parsed['dims'])} dimensions")
    print(f"Writing {args.output}")
    emit_cdl(parsed, args.output, args.commit, args.output_nc)
    print(f"Done. {n} variables written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
