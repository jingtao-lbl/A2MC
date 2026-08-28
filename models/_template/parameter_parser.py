"""Template ParameterParser — copy + fill in for your model.

Each adapter ships a parameter parser that reads the model's parameter file
(CDL / JSON / YAML / NetCDF / namelist / ...) and emits a uniform dict of
parameter records.

For FATES: see `rag/parameter_parser.py:FATESParameterParser` (will move to
`models/fates/parameter_parser.py` during Step E generalization). The parser
reads CDL or JSON, identifies parameter names matching the spec's
`param_name_regex`, extracts default values + dimensions + units, and
classifies into the spec's `param_categories` from the parameter name prefix.

The validator framework (V1, V2 per Doc 19 §6.5) calls this parser through
`spec.parameter_parser_class`. Returning anything that doesn't conform to the
expected dict shape will cause validators to crash or produce noisy output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class TemplateParameterParser:
    """Parses parameter files into a uniform dict of records.

    TODO(adapter-kit): implement parse() and the supporting helpers for your
    model. The expected output shape:

        {
            "param_name_1": {
                "name": "param_name_1",
                "default": <value or array>,
                "dimensions": ["dim1", "dim2"],     # NetCDF/CDL dim names
                "units": "kg/m2/s",
                "long_name": "Human-readable description",
                "category": "alloc",                # from spec.param_categories
            },
            ...
        }

    See `rag/parameter_parser.py:FATESParameterParser` for the FATES reference.
    """

    def parse(self, param_file: Path) -> Dict[str, Dict[str, Any]]:
        """Parse the parameter file at `param_file` into a dict keyed on name.

        TODO(adapter-kit): replace with real parsing.
        """
        raise NotImplementedError(
            "TemplateParameterParser.parse is a stub. "
            "Fill it in for your model. See models/_template/parameter_parser.py "
            "and the FATES reference (rag/parameter_parser.py:FATESParameterParser)."
        )

    # ---- Optional helpers (FATES reference) ----

    # TODO(adapter-kit): if your model has multiple parameter file formats
    # (e.g., CDL for older versions, JSON for newer), dispatch from parse()
    # to format-specific helpers like _parse_cdl(), _parse_json(), etc.
