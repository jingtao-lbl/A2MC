"""Tests for ``scripts/run_smoke_ensemble.py``'s input-format handling.

The script's compat gate asks "which variables does the input file provide, and does the binary
read any it lacks". That question presumes a flat variable namespace, which two of the kit's four
models have and two do not. Until 2026-08-27 the dispatch was on the file SUFFIX and raised
``ValueError`` on anything that was not ``.nc`` or ``.json`` -- the fourth instance of the same
first-model assumption already fixed in the materializer, the pre-submit validator, the Phase-2
CLI and the Y-matrix writer.

The tests below pin the two properties that fix depends on: dispatch is on CONTENT, and an
unenumerable format yields "gate not applicable" rather than a crash.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.run_smoke_ensemble import _input_file_vars, _is_netcdf  # noqa: E402

NETCDF3_MAGIC = b"CDF\x01" + b"\x00" * 32
HDF5_MAGIC = b"\x89HDF\r\n\x1a\n" + b"\x00" * 32


def test_a_text_deck_yields_gate_not_applicable_rather_than_raising(tmp_path):
    """A PFLOTRAN deck has no flat variable namespace, so the question has no answer.

    Returning None lets the caller say "n/a"; raising would abort a smoke run over a gate that
    was never applicable to this model in the first place.
    """
    deck = tmp_path / "pflotran.in"
    deck.write_text("SIMULATION\n  SIMULATION_TYPE SUBSURFACE\nEND\n")
    assert _input_file_vars(deck) is None


def test_dispatch_is_on_content_not_suffix_for_json(tmp_path):
    """A JSON parameter file named `.in` must still be enumerated.

    Suffix dispatch would have called this an unknown format. The FATES api-43 parameter file is
    JSON, and nothing guarantees a case names it `.json`.
    """
    p = tmp_path / "params.in"
    p.write_text(json.dumps({"fates_leaf_vcmax25top": 1.0, "fates_pftname": "x"}))
    assert _input_file_vars(p) == {"fates_leaf_vcmax25top", "fates_pftname"}


def test_dispatch_is_on_content_not_suffix_for_netcdf(tmp_path):
    """Both NetCDF magics are recognised regardless of the file's name."""
    for name, magic in (("classic.txt", NETCDF3_MAGIC), ("hdf5backed.dat", HDF5_MAGIC)):
        p = tmp_path / name
        p.write_bytes(magic)
        assert _is_netcdf(p), f"{name} should sniff as NetCDF"


def test_a_plain_text_file_is_not_mistaken_for_netcdf(tmp_path):
    """The sniff must be able to say NO -- otherwise it is not a check.

    'CDF' as the first three bytes is the classic-NetCDF signature; a deck that merely CONTAINS
    the letters must not match.
    """
    p = tmp_path / "deck.in"
    p.write_text("# a comment mentioning CDF and HDF5\nCHEMISTRY\nEND\n")
    assert _is_netcdf(p) is False


def test_a_json_list_yields_an_empty_set_not_none(tmp_path):
    """Valid JSON that is not an object has an ANSWER: it provides no named variables.

    That is different from "cannot be enumerated", and collapsing the two would report the wrong
    reason to the user.
    """
    p = tmp_path / "params.json"
    p.write_text(json.dumps([1, 2, 3]))
    assert _input_file_vars(p) == set()


def test_a_missing_file_does_not_raise(tmp_path):
    """`_is_netcdf` swallows the OSError; enumeration then reports unenumerable."""
    p = tmp_path / "nope.in"
    assert _is_netcdf(p) is False
    assert _input_file_vars(p) is None
