"""PFLOTRAN output parser — reads the mass-balance file (`*-mas.dat`).

PFLOTRAN has no NetCDF history tape and therefore no output CDL. Its primary
calibration-target surface is the **mass-balance file**, whose format has two
properties that will silently break a naive reader. Both were verified against
source AND against the real miniLEO output file (dev log `20260731d` §4):

1. **IT IS NOT A CSV.** The header is comma-separated and quoted; the DATA ROWS
   are fixed-width ``es16.8`` with **zero separators**
   (`output_aux.F90:1399-1412` header vs `output_observation.F90:2974-2975`
   data). Measured on the real file: 331 commas in the header, **0** in row 2.
   ``read_csv(sep=',')`` yields one giant column.

2. **CUMULATIVE vs RATE IS DECIDED BY THE UNITS BRACKET.** A coupler emits two
   columns whose variable STEM is identical, differing only in units
   (`output_observation.F90:2617-2622`):

       "east Water Mass [kg]"     -> cumulative, a running integral from t=0,
                                     never reset (`richards.F90:573-576`)
       "east Water Mass [kg/h]"   -> INSTANTANEOUS rate (per-second x tconv),
                                     NOT an interval average

   In the miniLEO file these are columns 104 and 106. The two FULL headers are
   distinct strings, and all 332 headers in that file are unique — so the full
   header text IS a valid key. What is ambiguous is the variable STEM
   ("east Water Mass"), which is why `find()` requires scope+variable+rate
   rather than a name alone.

Sign convention: **positive = INTO the domain** for every boundary-condition and
source/sink column, applied at write time
(`output_observation.F90:3290, 3314, …`). ``Global`` / ``Region`` columns are
inventories and are written unnegated.

Contract (docs/19 §6.5 + `tools/adapter_conformance_validator.py`): no-arg
``__init__`` + ``parse(file_path)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# "east Water Mass [kg/h]" -> ("east Water Mass", "kg/h")
_COL_RE = re.compile(r"^\s*(?P<name>.*?)\s*(?:\[(?P<units>[^\]]*)\])?\s*$")
# A units string containing '/' is a RATE (kg/h, mol/h); otherwise cumulative.
_RATE_RE = re.compile(r"/")

# Column families, by header prefix.
_GLOBAL_PREFIX = "Global "
_REGION_PREFIX = "Region "
_TIME_COLS = {"Time", "dt_flow", "dt_tran"}

_CATEGORY_RULES: Tuple[Tuple[str, str], ...] = (
    ("Water Mass", "water_flux"),
    ("Air Mass", "water_flux"),
    ("Total Mass", "water_flux"),
    ("Saturation", "state"),
    ("Pressure", "state"),
    ("Porosity", "state"),
    ("Permeability", "state"),
    ("(gas phase)", "gas"),
    ("(g)", "gas"),
)
# Mineral names carry no marker, so anything left that is not an aqueous ion is
# classified by the caller; the default below is the honest one.
_DEFAULT_CATEGORY = "solute"


@dataclass
class PFLOTRANOutputVariable:
    """One column of a `*-mas.dat` file."""
    name: str                  # full header text, e.g. 'east Water Mass [kg/h]'
    variable: str              # 'Water Mass'
    units: str                 # 'kg/h'
    scope: str                 # 'east' | 'all' | '' (global) | 'Time'
    family: str                # 'time' | 'global' | 'region' | 'coupler'
    column_index: int

    @property
    def is_rate(self) -> bool:
        """True if the units bracket denotes a rate.

        The units bracket is what distinguishes the two forms; the variable STEM
        is shared between them. (The full headers ARE distinct — all 332 are
        unique in the miniLEO file — so this is about the stem, not the header.)"""
        return bool(_RATE_RE.search(self.units))

    @property
    def is_cumulative(self) -> bool:
        """A running integral from t=0, never reset (`richards.F90:573-576`)."""
        return self.family in ("coupler", "region", "global") and not self.is_rate

    @property
    def positive_is_into_domain(self) -> bool:
        """Sign convention. Couplers are negated at write time so positive = in;
        Global/Region inventories are written unnegated and carry no direction."""
        return self.family == "coupler"

    @property
    def dimension_level(self) -> str:
        """The model's grouping axis is the mesh REGION, not a PFT."""
        return {"time": "scalar", "global": "domain",
                "region": "region", "coupler": "boundary"}.get(self.family, "unknown")

    @property
    def long_name(self) -> str:
        """Human-readable description, for RAG chunk text and any consumer that
        wants more than a column header.

        Composed from the header decomposition this class already performs
        (family / scope / variable / units / rate-ness), so it carries the two
        things a bare header does not state and a reader most often gets wrong:
        whether the column is an INSTANTANEOUS RATE or a RUNNING INTEGRAL, and
        which way the SIGN points.

        (Added 2026-08-01: `long_name` was declared here and populated on 0 of
        332 records, flagged by `tools/validate_adapter_parser_contract.py` on
        its first run against this adapter.)
        """
        units = f" [{self.units}]" if self.units else ""

        if self.family == "time":
            label = {"Time": "Simulation time",
                     "dt_flow": "Flow-solver timestep size",
                     "dt_tran": "Transport-solver timestep size"}.get(
                         self.variable, self.variable)
            return f"{label}{units}"

        if self.family == "coupler":
            kind = ("instantaneous rate of" if self.is_rate
                    else "cumulative (running integral from t=0)")
            sign = ("; POSITIVE IS INTO THE DOMAIN, so outflow is negative"
                    if self.positive_is_into_domain else "")
            return (f"{kind} {self.variable} across boundary coupler "
                    f"{self.scope!r}{units}{sign}")

        if self.family == "global":
            return f"Domain-total {self.variable} inventory{units}"

        if self.family == "region":
            return f"{self.variable} over mesh region {self.scope!r}{units}"

        return f"{self.variable}{units}"

    @property
    def category(self) -> str:
        for kw, cat in _CATEGORY_RULES:
            if kw in self.name:
                return cat
        return "" if self.family == "time" else _DEFAULT_CATEGORY

    def __repr__(self) -> str:  # pragma: no cover
        kind = "rate" if self.is_rate else "cumulative"
        return f"<PFLOTRANOutputVariable {self.name!r} {kind} col={self.column_index}>"


class PFLOTRANOutputParser:
    """Parses a PFLOTRAN `*-mas.dat` header into an output-variable inventory."""

    def __init__(self):
        self._vars: Dict[str, PFLOTRANOutputVariable] = {}

    # -- public ------------------------------------------------------------
    def parse(self, file_path) -> Dict[str, PFLOTRANOutputVariable]:
        """Inventory the columns. Reads ONLY the header line."""
        path = Path(file_path)
        with path.open(errors="replace") as fh:
            header = fh.readline()
        if not header.strip():
            raise ValueError(f"empty header in {path}")

        self._vars = {}
        for idx, raw in enumerate(header.split(",")):
            col = raw.strip().strip('"').strip()
            if not col:
                continue
            m = _COL_RE.match(col)
            name_part = (m.group("name") or col).strip() if m else col
            units = (m.group("units") or "").strip() if m else ""

            if name_part in _TIME_COLS or name_part.startswith(("Time", "dt_")):
                family, scope, variable = "time", name_part, name_part
            elif name_part.startswith(_GLOBAL_PREFIX):
                family, scope = "global", ""
                variable = name_part[len(_GLOBAL_PREFIX):].strip()
            elif name_part.startswith(_REGION_PREFIX):
                family = "region"
                rest = name_part[len(_REGION_PREFIX):].strip()
                scope, _, variable = rest.partition(" ")
                variable = variable.strip() or rest
            else:
                # Coupler columns are '<coupler_name> <variable>'; the coupler name
                # is deck-defined (east / top_vent / top_recharge in miniLEO), so
                # it cannot be enumerated -- take the first token.
                family = "coupler"
                scope, _, variable = name_part.partition(" ")
                variable = variable.strip() or name_part

            self._vars[col] = PFLOTRANOutputVariable(
                name=col, variable=variable, units=units, scope=scope,
                family=family, column_index=idx)
        return self._vars

    def _require_parsed(self):
        if not self._vars:
            raise RuntimeError("call parse() first")

    # -- convenience -------------------------------------------------------
    def find(self, scope: str, variable: str, rate: bool) -> Optional[PFLOTRANOutputVariable]:
        """Resolve the ONE column matching scope+variable+rate-ness.

        This is the API that keeps callers honest: asking by variable STEM alone
        is ambiguous by construction, because the cumulative and rate columns
        share a stem. (A full header is unambiguous — use ``parse()`` keys for
        that; ``find()`` exists for when you have scope+variable, not a header.)
        """
        self._require_parsed()
        hits = [v for v in self._vars.values()
                if v.scope == scope and v.variable == variable and v.is_rate == rate]
        if len(hits) > 1:
            raise ValueError(f"ambiguous: {len(hits)} columns match "
                             f"scope={scope!r} variable={variable!r} rate={rate}")
        return hits[0] if hits else None

    def read_series(self, file_path, columns: List[PFLOTRANOutputVariable]
                    ) -> Dict[str, List[float]]:
        """Read the requested columns' time series from the DATA rows.

        Splits on WHITESPACE, not commas: the data rows are fixed-width with no
        separators (see module docstring). Rows whose field count does not match
        the header are skipped rather than mis-aligned, because a short row means
        the run was interrupted mid-write.
        """
        self._require_parsed()
        path = Path(file_path)
        want = {c.column_index: c.name for c in columns}
        out: Dict[str, List[float]] = {c.name: [] for c in columns}
        ncol = len(self._vars)
        with path.open(errors="replace") as fh:
            fh.readline()                                   # discard header
            for line in fh:
                fields = line.split()
                if len(fields) != ncol:
                    continue
                for idx, name in want.items():
                    try:
                        out[name].append(float(fields[idx]))
                    except (ValueError, IndexError):
                        pass
        return out
