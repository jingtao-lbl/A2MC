"""EcoSIM parameter parser.

Reads an EcoSIM input file (parameter/site NetCDF or JSON) and returns a uniform
dict of parameter records.

Interface follows the A2MC adapter contract (`models/_template/parameter_parser.py`
and `tools/adapter_conformance_validator.py`): a **no-arg constructor** plus
`parse(file_path)`. (The legacy `rag/parameter_parser.py:FATESParameterParser`
takes the path in its constructor; that is the pre-adapter-kit shape and is being
generalized in Doc 19 Step E. New adapters use the contract shape so validators
V1/V2 can dispatch through `spec.parameter_parser_class`.)

Key differences from FATES
--------------------------
1. No name prefix. FATES filters on `fates_*`; EcoSIM parameter names are bare
   Fortran identifiers (`VCMX`, `XKCO2`, `ICTYP`). Every variable is a candidate
   parameter; string/char variables are still recorded but flagged `is_string`
   so downstream calibratable filters drop them.
2. PFT axis has several spellings across EcoSIM input files: `npfts` (pft input),
   `npft` (reference table), `pft` (output tape), `maxpfts` (JSON).
3. Categories are inferred from `long_name` (grounded in the real long_names in
   the EcoSIM pft file); default "other". The curated YAML (pipeline Step 3)
   carries the authoritative mechanism grouping.

Supported formats: `.nc` (netCDF4) and `.json` (EcoSIM's NetCDF-mirror schema).
`.cdl` raises NotImplementedError for now (the examples ship `.nc.cdl`; wiring
those in is a follow-up).

Author: Jing Tao with Claude
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# PFT-axis dimension names seen across EcoSIM input files.
PFT_AXIS_NAMES = {"npfts", "npft", "pft", "maxpfts"}

# Coarse category inference from long_name keywords. Grounded in the actual
# long_names in ds_input__pft_test__ex1.nc; default "other".
CATEGORY_KEYWORDS: List[Tuple[str, str]] = [
    ("rubisco", "photosynthesis"),
    ("carboxylase", "photosynthesis"),
    ("oxygenase", "photosynthesis"),
    ("chlorophyll", "photosynthesis"),
    ("chl", "photosynthesis"),
    ("pep", "photosynthesis"),
    ("photosynthesis", "photosynthesis"),
    ("stomat", "stomatal"),
    ("albedo", "radiation"),
    ("transmission", "radiation"),
    ("phenology", "phenology"),
    ("node initiation", "phenology"),
    ("leaf appearance", "phenology"),
    ("chilling", "phenology"),
    ("photoperiod", "phenology"),
    ("allocation", "allocation"),
    ("partition", "allocation"),
    ("turnover", "turnover"),
    ("storage organ", "allocation"),
    ("root", "roots"),
    ("mycorrhiz", "nutrient"),
    ("n2 fixation", "nutrient"),
    ("nitrogen", "nutrient"),
    ("phosph", "nutrient"),
    ("respiration", "respiration"),
    ("growth habit", "pfts"),
    ("thermal adaptation", "temperature"),
]


@dataclass
class EcoSIMParameter:
    """A single EcoSIM parameter with metadata."""

    name: str
    dimensions: List[str] = field(default_factory=list)
    units: str = "unknown"
    long_name: str = ""
    data_type: str = "double"
    default_values: Optional[Any] = None
    source_file: str = ""

    @property
    def category(self) -> str:
        ln = self.long_name.lower()
        for kw, cat in CATEGORY_KEYWORDS:
            if kw in ln:
                return cat
        return "other"

    @property
    def category_key(self) -> str:
        return self.category

    @property
    def is_pft_specific(self) -> bool:
        return any(d in PFT_AXIS_NAMES for d in self.dimensions)

    @property
    def is_scalar(self) -> bool:
        return len(self.dimensions) == 0

    @property
    def is_string(self) -> bool:
        return self.data_type in ("string", "char")

    def __repr__(self) -> str:
        dims = f"({', '.join(self.dimensions)})" if self.dimensions else "(scalar)"
        return f"EcoSIMParameter({self.name}{dims})"


class EcoSIMParameterParser:
    """Parse EcoSIM parameter/input files (.nc, .json) into EcoSIMParameter records.

    Adapter-contract interface: construct with no args, then call
    ``parse(file_path)``. Convenience accessors (get_dimensions, get_pft_count,
    …) operate on the most recent parse and raise if called before ``parse``.
    """

    def __init__(self):
        self._parameters: Optional[Dict[str, EcoSIMParameter]] = None
        self._dimensions: Optional[Dict[str, int]] = None

    def parse(self, file_path) -> Dict[str, EcoSIMParameter]:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Parameter file not found: {file_path}")
        suffix = file_path.suffix.lower()
        if suffix == ".nc":
            self._parameters, self._dimensions = self._parse_nc(file_path)
        elif suffix == ".json":
            self._parameters, self._dimensions = self._parse_json(file_path)
        elif suffix == ".cdl":
            raise NotImplementedError(
                "EcoSIM .cdl parsing not implemented yet. The examples/ suite "
                "ships .nc.cdl companions; wiring these in is a follow-up. Use "
                "the .nc or .json input directly for now."
            )
        else:
            raise ValueError(f"Unsupported EcoSIM parameter format: {suffix}")
        return self._parameters

    def _require_parsed(self):
        if self._parameters is None:
            raise RuntimeError("call parse(file_path) before using accessors")

    def get_dimensions(self) -> Dict[str, int]:
        self._require_parsed()
        return self._dimensions

    def get_pft_count(self) -> int:
        self._require_parsed()
        for name in ("npfts", "npft", "pft", "maxpfts"):
            if name in self._dimensions:
                return self._dimensions[name]
        return 0

    def get_parameters_by_category(self) -> Dict[str, List[EcoSIMParameter]]:
        self._require_parsed()
        by_cat: Dict[str, List[EcoSIMParameter]] = {}
        for p in self._parameters.values():
            by_cat.setdefault(p.category_key, []).append(p)
        return by_cat

    def get_pft_parameters(self) -> List[EcoSIMParameter]:
        self._require_parsed()
        return [p for p in self._parameters.values() if p.is_pft_specific]

    def get_scalar_parameters(self) -> List[EcoSIMParameter]:
        self._require_parsed()
        return [p for p in self._parameters.values() if p.is_scalar]

    # =========================================================================
    # NetCDF parser
    # =========================================================================

    def _parse_nc(self, file_path: Path) -> Tuple[Dict[str, EcoSIMParameter], Dict[str, int]]:
        try:
            import netCDF4 as nclib
        except ImportError:
            raise ImportError("netCDF4 required for parsing EcoSIM .nc files")
        ds = nclib.Dataset(file_path, "r")
        dimensions = {name: len(dim) for name, dim in ds.dimensions.items()}
        parameters: Dict[str, EcoSIMParameter] = {}
        for var_name, var in ds.variables.items():
            dims = list(var.dimensions)
            data_type = self._normalize_dtype(str(var.dtype))
            if data_type == "string":
                dims = [d for d in dims if not d.lower().startswith(("nchar", "string"))]
            try:
                if data_type == "string":
                    default_values = self._decode_char(var)
                else:
                    default_values = var[:].tolist()
            except Exception:
                default_values = None
            parameters[var_name] = EcoSIMParameter(
                name=var_name,
                dimensions=dims,
                units=getattr(var, "units", "unknown"),
                long_name=getattr(var, "long_name", ""),
                data_type=data_type,
                default_values=default_values,
                source_file=file_path.name,
            )
        ds.close()
        return parameters, dimensions

    @staticmethod
    def _decode_char(var) -> List[str]:
        raw = var[:]
        out: List[str] = []
        try:
            for row in raw:
                if hasattr(row, "__iter__"):
                    out.append(b"".join(
                        c if isinstance(c, bytes) else str(c).encode()
                        for c in row
                    ).decode("utf-8", "ignore").strip())
                else:
                    out.append(str(row).strip())
        except Exception:
            return []
        return out

    # =========================================================================
    # JSON parser  (EcoSIM schema: {global_attributes, dimensions, variables})
    # =========================================================================

    def _parse_json(self, file_path: Path) -> Tuple[Dict[str, EcoSIMParameter], Dict[str, int]]:
        with open(file_path) as f:
            data = json.load(f)
        raw_dims = data.get("dimensions", {})
        dimensions = {k: (-1 if v == "UNLIMITED" else int(v)) for k, v in raw_dims.items()}
        parameters: Dict[str, EcoSIMParameter] = {}
        for name, info in data.get("variables", {}).items():
            attrs = info.get("attributes", {})
            parameters[name] = EcoSIMParameter(
                name=name,
                dimensions=list(info.get("dimensions", [])),
                units=attrs.get("units", "unknown"),
                long_name=attrs.get("long_name", ""),
                data_type=self._normalize_dtype(info.get("dtype", "float")),
                default_values=info.get("data", None),
                source_file=file_path.name,
            )
        return parameters, dimensions

    # =========================================================================
    # Shared
    # =========================================================================

    @staticmethod
    def _normalize_dtype(dtype_str: str) -> str:
        d = dtype_str.lower()
        if d.startswith("|s") or "str" in d or d == "object" or d.startswith("s"):
            return "string"
        if "char" in d:
            return "string"
        if "float64" in d or d == "double":
            return "double"
        if "float" in d:
            return "double"
        if "int" in d:
            return "int"
        return "double"
