"""ATS parameter parser — reads a Trilinos/Teuchos ParameterList XML input deck.

ATS has NO single parameter file. Calibration knobs are ``<Parameter>`` leaves
scattered across a nested ``<ParameterList>`` XML deck (the "Amanzi spec"). A knob
is therefore addressed by its **full ParameterList path**, not a bare name — the same
physical parameter (e.g. van Genuchten alpha) recurs once per mesh region/material.

This parser flattens a deck into a uniform dict of records keyed on that path address:

    {
        "state/evaluators/permeability/value": {
            "name": "state/evaluators/permeability/value",   # the address (unique key)
            "leaf": "value",                                 # the <Parameter> name
            "path": ["state", "evaluators", "permeability"], # ancestor ParameterList names
            "default": 2e-13,
            "dimensions": [],                                # scalar; region name if region-keyed
            "units": "m^2",
            "long_name": "permeability",
            "category": "permeability",                      # from spec.param_categories
            "xml_type": "double",
            "region": "permeability",                        # nearest region/block ancestor
            "calibratable": True,                            # numeric + physical category
        },
        ...
    }

Units are parsed from the ``[...]`` in the leaf name (e.g. ``alpha [Pa^-1]``) or from a
sibling ``units`` Parameter. Only numeric leaves (``double`` / ``int``) become records.

The address helpers (:func:`iter_parameters`, :func:`format_address`,
:func:`set_parameter_values`) are shared with ``backend.write_parameter_file`` so parse
and write use one addressing scheme.

Contract: no-arg ``__init__`` + ``parse(file_path)`` (adapter-kit Footgun 1).
Grounded in real decks under ``models/ats/tests/fixtures/`` (COMPASS oakharbor_*,
ats-demos priestley_taylor) and the wiki at ``docs/ats-knowledge-base/``.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

# Teuchos numeric scalar types we treat as calibratable knobs.
_NUMERIC_TYPES = {"double", "float", "int"}
_UNIT_RE = re.compile(r"\[([^\]]+)\]")

# Keyword -> category. Ordered; first hit on the joined path+leaf wins.
_CATEGORY_RULES: Tuple[Tuple[str, str], ...] = (
    ("van genuchten", "water_retention"),
    ("brooks-corey", "water_retention"),
    ("brooks corey", "water_retention"),
    ("wrm", "water_retention"),
    ("residual saturation", "water_retention"),
    ("residual sat", "water_retention"),
    ("permeability", "permeability"),
    ("porosity", "porosity"),
    ("compressibility", "porosity"),
    ("manning", "surface_flow"),
    ("overland conductivity", "surface_flow"),
    ("priestley", "evapotranspiration"),
    ("rooting depth", "evapotranspiration"),
    ("transpiration", "evapotranspiration"),
    ("evapo", "evapotranspiration"),
    ("thermal conduct", "thermal"),
    ("density", "fluid_property"),
    ("viscosity", "fluid_property"),
    ("molar mass", "fluid_property"),
)

# Physical categories that are legitimate calibration knobs (vs solver/IO/numeric control).
_PHYSICAL_CATEGORIES = {
    "water_retention", "permeability", "porosity",
    "surface_flow", "evapotranspiration", "thermal", "fluid_property",
}

# Ancestor list names that mark a region/material block boundary (for multiplicity).
_REGION_PARENTS = {"wrm parameters", "model parameters", "water retention model parameters"}


def _classify(path: List[str], leaf: str) -> str:
    """Infer a category from the address text; '' if nothing physical matched."""
    hay = " ".join(path + [leaf]).lower()
    for kw, cat in _CATEGORY_RULES:
        if kw in hay:
            return cat
    return ""


def _units_for(leaf: str, siblings_units: str) -> str:
    m = _UNIT_RE.search(leaf)
    if m:
        return m.group(1).strip()
    return siblings_units


def iter_parameters(root: ET.Element) -> Iterator[Tuple[List[str], ET.Element]]:
    """Yield ``(path, parameter_element)`` for every ``<Parameter>`` leaf.

    ``path`` is the list of ancestor ``<ParameterList>`` names (the root list's own
    name — usually "Main" — is dropped so addresses start at the first real section).
    Shared by parse() and the backend writer.
    """

    def _walk(elem: ET.Element, path: List[str]) -> Iterator[Tuple[List[str], ET.Element]]:
        for child in elem:
            tag = child.tag.rsplit("}", 1)[-1]  # strip any XML namespace
            name = child.get("name", "")
            if tag == "Parameter":
                yield path, child
            elif tag == "ParameterList":
                yield from _walk(child, path + [name])

    # Drop the root list's own name from the path.
    root_tag = root.tag.rsplit("}", 1)[-1]
    if root_tag == "ParameterList":
        yield from _walk(root, [])
    else:
        yield from _walk(root, [])


def format_address(path: List[str], leaf: str) -> str:
    """Canonical, human-readable, unique knob address: ``a/b/c/leaf``."""
    return "/".join([*path, leaf])


class ATSParameterParser:
    """Parses an ATS ParameterList XML deck into a uniform dict of records."""

    def parse(self, param_file: Path) -> Dict[str, Dict[str, Any]]:
        param_file = Path(param_file)
        tree = ET.parse(param_file)
        root = tree.getroot()

        # First pass: collect, per ParameterList path, a 'units' sibling if present,
        # so a value/leaf without a bracketed unit can borrow its list's units param.
        units_by_path: Dict[Tuple[str, ...], str] = {}
        for path, p in iter_parameters(root):
            if p.get("name") == "units":
                units_by_path[tuple(path)] = (p.get("value") or "").strip()

        records: Dict[str, Dict[str, Any]] = {}
        for path, p in iter_parameters(root):
            xml_type = (p.get("type") or "").strip()
            if xml_type not in _NUMERIC_TYPES:
                continue
            leaf = p.get("name", "")
            raw_val = (p.get("value") or "").strip()
            try:
                default: Any = int(raw_val) if xml_type == "int" else float(raw_val)
            except ValueError:
                continue  # not a plain scalar (skip)

            address = format_address(path, leaf)
            category = _classify(path, leaf)
            region = path[-1] if path else ""
            # If the parent block is a region container, the region is the immediate parent.
            dims: List[str] = []
            if len(path) >= 2 and path[-2].lower() in _REGION_PARENTS:
                region = path[-1]
                dims = [region]

            records[address] = {
                "name": address,
                "leaf": leaf,
                "path": list(path),
                "default": default,
                "dimensions": dims,
                "units": _units_for(leaf, units_by_path.get(tuple(path), "")),
                "long_name": leaf,
                "category": category,
                "xml_type": xml_type,
                "region": region,
                "calibratable": category in _PHYSICAL_CATEGORIES,
            }
        return records

    def calibration_parameters(self, param_file: Path) -> Dict[str, Dict[str, Any]]:
        """Convenience: only the physical (calibratable) knobs."""
        return {k: v for k, v in self.parse(param_file).items() if v["calibratable"]}


def set_parameter_values(root: ET.Element, modifications: Dict[str, Any]) -> List[str]:
    """Set ``<Parameter value=...>`` in-place for each address→value in ``modifications``.

    Returns the list of addresses that were NOT found (so the caller can fail loud).
    Shared with :meth:`ATSParameterParser.parse` via the same addressing scheme.
    """
    index: Dict[str, ET.Element] = {}
    for path, p in iter_parameters(root):
        index[format_address(path, p.get("name", ""))] = p

    missing: List[str] = []
    for address, new_value in modifications.items():
        elem = index.get(address)
        if elem is None:
            missing.append(address)
            continue
        elem.set("value", repr(new_value) if isinstance(new_value, float) else str(new_value))
    return missing
