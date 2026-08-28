"""Template OutputParser — copy + fill in for your model.

Each adapter ships an output parser that reads the model's history-output
inventory (typically a CDL produced by `ncdump -h <output>.nc`) and emits a
uniform dict of output-variable records.

For FATES: see `rag/output_parser.py:FATESOutputParser` (will move to
`models/fates/output_parser.py` during Step E generalization). The parser
identifies variable names matching the spec's `output_name_regex`, extracts
dimensions + units + long_name, and classifies into the spec's
`output_categories` from the variable name prefix.

The validator framework (V1, V2 per Doc 19 §6.5) calls this parser through
`spec.output_parser_class`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class TemplateOutputParser:
    """Parses output-variable files into a uniform dict of records.

    TODO(adapter-kit): implement parse() for your model. The expected output shape:

        {
            "VAR_NAME_1": {
                "name": "VAR_NAME_1",
                "dimensions": ["time", "fates_pft", "lat", "lon"],
                "units": "kg/m2",
                "long_name": "Human-readable description",
                "cell_methods": "time: mean",       # if applicable
                "category": "biomass",              # from spec.output_categories
            },
            ...
        }

    See `rag/output_parser.py:FATESOutputParser` for the FATES reference.
    """

    def parse(self, output_cdl: Path) -> Dict[str, Dict[str, Any]]:
        """Parse the output CDL at `output_cdl` into a dict keyed on variable name.

        TODO(adapter-kit): replace with real parsing.
        """
        raise NotImplementedError(
            "TemplateOutputParser.parse is a stub. "
            "Fill it in for your model. See models/_template/output_parser.py "
            "and the FATES reference (rag/output_parser.py:FATESOutputParser)."
        )
