"""ATS output parser — the calibration-target surface.

ATS does NOT write NetCDF history tapes. Its calibration-target channel is the deck's
``observations`` block, which declares comma-delimited time-series ``.dat`` files. A target
therefore has to be **pre-declared** in the deck; ATS will not emit an undeclared variable.

So the authoritative "output inventory" for ATS is the ``observations`` block of an input
deck. This parser reads it into the uniform output-record shape:

    {
        "surface-total_evapotranspiration": {
            "name": "surface-total_evapotranspiration",
            "dimensions": ["time"],
            "units": "",
            "long_name": "surface-total_evapotranspiration",
            "category": "evapotranspiration",
            "region": "surface domain",
            "functional": "average",
            "location": "cell",
            "output_filename": "water_balance.dat",
        },
        ...
    }

``parse()`` dispatches on file suffix:
    * ``.xml`` deck  -> read the ``observations`` block (the primary, authoritative path)
    * ``.dat`` file  -> read the observation-file header columns (a completed run's tape)

Contract: no-arg ``__init__`` + ``parse(file_path)``. Grounded in real decks under
``models/ats/tests/fixtures/`` (oakharbor_transect emits ``water_balance.dat``).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

from .parameter_parser import iter_parameters

_UNIT_RE = re.compile(r"\[([^\]]+)\]")

# Keyword -> output category, matched against the ATS field name.
_CATEGORY_RULES = (
    ("evapotranspiration", "evapotranspiration"),
    ("evaporation", "evapotranspiration"),
    ("transpiration", "evapotranspiration"),
    ("water_table", "water_table"),
    ("ponded_depth", "surface_water"),
    ("surface-water_flux", "runoff"),
    ("runoff", "runoff"),
    ("water_content", "water_storage"),
    ("water_source", "water_flux"),
    ("subsurface_flux", "water_flux"),
    ("saturation", "saturation"),
    ("pressure", "pressure"),
    ("temperature", "thermal"),
    ("snow", "snow"),
    ("precipitation", "forcing"),
)


def _classify(field: str) -> str:
    f = field.lower()
    for kw, cat in _CATEGORY_RULES:
        if kw in f:
            return cat
    return ""


class ATSOutputParser:
    """Parses the ATS observation surface into a uniform dict of output records."""

    def parse(self, output_file: Path) -> Dict[str, Dict[str, Any]]:
        output_file = Path(output_file)
        if output_file.suffix.lower() == ".xml":
            return self._parse_xml_observations(output_file)
        return self._parse_dat(output_file)

    # ---- Primary path: the deck's observations block ----

    def _parse_xml_observations(self, deck: Path) -> Dict[str, Dict[str, Any]]:
        root = ET.parse(deck).getroot()

        # Group the flat (path, Parameter) stream by the enclosing observation sub-list,
        # so each observation entry's variable/region/functional/location travel together.
        # An observation entry is the deepest ParameterList that carries a "variable" leaf.
        entries: Dict[str, Dict[str, str]] = {}
        filename_by_path: Dict[str, str] = {}
        for path, p in iter_parameters(root):
            joined = "/".join(path)
            name = p.get("name", "")
            val = (p.get("value") or "").strip()
            # Only look inside an "observations" section.
            if "observations" not in joined.lower():
                continue
            if name == "observation output filename":
                filename_by_path[joined] = val
            if name in ("variable", "region", "functional", "location name"):
                entries.setdefault(joined, {})[name] = val

        # Resolve each entry's output filename = nearest ancestor path that declared one.
        def _filename_for(entry_path: str) -> str:
            best = ""
            best_len = -1
            for fpath, fname in filename_by_path.items():
                if entry_path == fpath or entry_path.startswith(fpath + "/"):
                    if len(fpath) > best_len:
                        best, best_len = fname, len(fpath)
            return best

        records: Dict[str, Dict[str, Any]] = {}
        for entry_path, fields in entries.items():
            variable = fields.get("variable")
            if not variable:
                continue
            region = fields.get("region", "")
            key = variable if variable not in records else f"{variable} [{region}]"
            records[key] = {
                "name": variable,
                "dimensions": ["time"],
                "units": "",
                "long_name": variable,
                "category": _classify(variable),
                "region": region,
                "functional": fields.get("functional", ""),
                "location": fields.get("location name", ""),
                "output_filename": _filename_for(entry_path),
            }
        return records

    # ---- Secondary path: a completed run's observation .dat header ----

    def _parse_dat(self, dat: Path) -> Dict[str, Dict[str, Any]]:
        """Best-effort: read column names from an ATS observation ``.dat`` file.

        ATS writes a comma-delimited file with a time column; header lines are prefixed
        with ``#``. The last ``#``-comment line before the data (or the first data line if
        quoted) carries the column names. This is a completed-run reader; the authoritative
        inventory comes from the deck (``_parse_xml_observations``).
        """
        header_cols: List[str] = []
        with open(dat, "r") as fh:
            last_comment = ""
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                if s.startswith("#"):
                    last_comment = s.lstrip("#").strip()
                    continue
                # First data-ish line: prefer the last comment as the header if it looks columnar.
                candidate = last_comment if ("," in last_comment) else s
                header_cols = [c.strip().strip('"') for c in candidate.split(",")]
                break

        records: Dict[str, Dict[str, Any]] = {}
        for col in header_cols:
            if not col:
                continue
            m = _UNIT_RE.search(col)
            units = m.group(1).strip() if m else ""
            name = _UNIT_RE.sub("", col).strip()
            records[name] = {
                "name": name,
                "dimensions": ["time"],
                "units": units,
                "long_name": col,
                "category": _classify(name),
                "region": "",
                "functional": "",
                "location": "",
                "output_filename": Path(dat).name,
            }
        return records
