"""EcoSIM output-variable parser.

Reads an EcoSIM output registry CDL (produced by
`scripts/extract_ecosim_outputs.py` from a sample h0 history tape) and returns a
uniform dict of output-variable records.

Interface follows the A2MC adapter contract: no-arg constructor + `parse(file_path)`
(see the note in `parameter_parser.py`).

EcoSIM-specific pieces:
    - Dimension-level map keyed on EcoSIM history dims (`pft`, `column`, `levsoi`,
      `levcan`, `nbranches`, `elements`, `nomcomplx`, `nkinecomp`, `ngrstages`, …).
    - A name-suffix convention that also signals the grouping axis: `_pft`, `_col`
      (column), `_vr` (soil layer), `_litr` (litter), `_brch` (branch).
    - Category inference from name keywords; default "other".

Author: Jing Tao with Claude
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


DIMENSION_LEVEL_MAP = {
    "pft": "pft",
    "npfts": "pft",
    "column": "column",
    "topounit": "topounit",
    "gridcell": "site",
    "levsoi": "soil_layer",
    "levcan": "canopy",
    "levsno": "snow_layer",
    "nbranches": "branch",
    "elements": "element",
    "ngrstages": "growth_stage",
    "nkinecomp": "kinetic_component",
    "nomcomplx": "som_complex",
    "pmorphunits": "morph_unit",
}

SUFFIX_LEVEL_MAP = [
    ("_pft", "pft"),
    ("_col", "column"),
    ("_vr", "soil_layer"),
    ("_litr", "litter"),
    ("_brch", "branch"),
]

OUTPUT_CATEGORIES = {
    "methanogen": "microbial",
    "Bacter": "microbial",
    "Fung": "microbial",
    "HetrBacter": "microbial",
    "Microb": "microbial",
    "AUTO_RESP": "carbon_flux",
    "HETR_RESP": "carbon_flux",
    "GPP": "carbon_flux",
    "NPP": "carbon_flux",
    "NEE": "carbon_flux",
    "RESP": "carbon_flux",
    "Acetate": "carbon_pool",
    "ATM_CO2": "atmosphere",
    "ATM_CH4": "atmosphere",
    "ATM_": "atmosphere",
    "AMENDED": "management",
    "FERT": "management",
    "TILL": "management",
    "ACTV_LYR": "soil_physical",
    "AIR_TEMP": "meteorology",
    "SOIL_TEMP": "soil_physical",
    "WATER": "hydrology",
    "WFLX": "hydrology",
    "LAI": "canopy",
    "BIOM": "biomass",
    "_C_": "carbon_pool",
    "_N_": "nitrogen_pool",
    "_P_": "phosphorus_pool",
    "UPTAKE": "nutrient",
    "NH4": "soil_nutrient",
    "NO3": "soil_nutrient",
    "PO4": "soil_nutrient",
}


@dataclass
class EcoSIMOutputVariable:
    """A single EcoSIM output variable."""

    name: str
    dimensions: List[str] = field(default_factory=list)
    units: str = ""
    long_name: str = ""
    data_type: str = "float"
    cell_methods: str = ""

    @property
    def dimension_level(self) -> str:
        for dim in self.dimensions:
            if dim in DIMENSION_LEVEL_MAP:
                return DIMENSION_LEVEL_MAP[dim]
        for suffix, level in SUFFIX_LEVEL_MAP:
            if self.name.endswith(suffix):
                return level
        non_standard = [d for d in self.dimensions
                        if d not in ("time", "gridcell", "topounit")]
        return "site" if not non_standard else "other"

    @property
    def category(self) -> str:
        for pattern in sorted(OUTPUT_CATEGORIES.keys(), key=len, reverse=True):
            if pattern in self.name:
                return OUTPUT_CATEGORIES[pattern]
        return "other"

    def __repr__(self) -> str:
        dims = f"({', '.join(self.dimensions)})" if self.dimensions else "(scalar)"
        return f"EcoSIMOutputVariable({self.name}{dims})"


class EcoSIMOutputParser:
    """Parse an EcoSIM output-registry CDL into EcoSIMOutputVariable records.

    Adapter-contract interface: construct with no args, then call
    ``parse(file_path)``.
    """

    def __init__(self):
        self._variables: Optional[Dict[str, EcoSIMOutputVariable]] = None
        self._dimensions: Optional[Dict[str, int]] = None

    def parse(self, file_path) -> Dict[str, EcoSIMOutputVariable]:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Output CDL file not found: {file_path}")
        content = file_path.read_text()
        self._dimensions = self._parse_dimensions(content)
        self._variables = {}

        var_pattern = re.compile(
            r'^\s+(float|double|int)\s+(\w+)\(([^)]+)\)\s*;',
            re.MULTILINE,
        )
        for m in var_pattern.finditer(content):
            data_type, name, dims_str = m.group(1), m.group(2), m.group(3)
            dims = [d.split("=")[0].strip() for d in dims_str.split(",")]
            self._variables[name] = EcoSIMOutputVariable(
                name=name, dimensions=dims, data_type=data_type,
            )
        self._parse_attributes(content)
        return self._variables

    def _require_parsed(self):
        if self._variables is None:
            raise RuntimeError("call parse(file_path) before using accessors")

    def _parse_dimensions(self, content: str) -> Dict[str, int]:
        dimensions: Dict[str, int] = {}
        dim_section = re.search(
            r'dimensions:\s*\n(.*?)(?=variables:|data:|$)', content, re.DOTALL,
        )
        if dim_section:
            for m in re.finditer(r'(\w+)\s*=\s*(\d+|UNLIMITED)', dim_section.group(1)):
                name, val = m.group(1), m.group(2)
                dimensions[name] = -1 if val == "UNLIMITED" else int(val)
        return dimensions

    def _parse_attributes(self, content: str):
        current_var = None
        var_decl = re.compile(r'^\s+(?:float|double|int)\s+(\w+)\(')
        attr = re.compile(r'^\s+:(\w+)\s*=\s*"([^"]*)"')
        for line in content.splitlines():
            m = var_decl.match(line)
            if m:
                current_var = m.group(1)
                continue
            m = attr.match(line)
            if m and current_var and current_var in self._variables:
                aname, aval = m.group(1), m.group(2)
                v = self._variables[current_var]
                if aname == "units":
                    v.units = aval
                elif aname == "long_name":
                    v.long_name = aval
                elif aname == "cell_methods":
                    v.cell_methods = aval
            elif line.strip() and not line.strip().startswith((":", "//")):
                current_var = None

    def get_dimensions(self) -> Dict[str, int]:
        self._require_parsed()
        return self._dimensions

    def get_variables_by_dimension(self) -> Dict[str, List[EcoSIMOutputVariable]]:
        self._require_parsed()
        by_dim: Dict[str, List[EcoSIMOutputVariable]] = {}
        for v in self._variables.values():
            by_dim.setdefault(v.dimension_level, []).append(v)
        return by_dim

    def get_variables_by_category(self) -> Dict[str, List[EcoSIMOutputVariable]]:
        self._require_parsed()
        by_cat: Dict[str, List[EcoSIMOutputVariable]] = {}
        for v in self._variables.values():
            by_cat.setdefault(v.category, []).append(v)
        return by_cat
