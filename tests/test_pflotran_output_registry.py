#!/usr/bin/env python
"""PFLOTRAN's committed output registry — the tape-free path to the same output surface.

`scripts/extract_pflotran_outputs.py` snapshots the mass-balance column surface into
`docs/pflotran-knowledge-base/pflotran_output_info_<commit>.json` so the RAG build no
longer depends on a 99 MB team bundle that lives outside this repo. Guards:

  * round-trip: the registry rebuilds the same inventory the parser reads from the tape;
  * the stored DERIVED fields still match what today's parser derives, so parser drift
    shows up as a registry diff rather than as silently different RAG chunk text;
  * the deck-scope warning is present — the registry describes ONE DECK's surface, and
    a reader who over-trusts it is the failure mode this artifact invites;
  * the RAG build's fallback selects the registry when the tape is absent, and prefers
    the tape when both exist.

Run:  ~/a2mc_env/bin/python -m pytest tests/test_pflotran_output_registry.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

from models.pflotran.output_parser import PFLOTRANOutputParser  # noqa: E402


def _load_script(name):
    spec = importlib.util.spec_from_file_location(f"_{name}", REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EX = _load_script("extract_pflotran_outputs")
REGISTRY = EX.default_registry_path()

_TAPE = os.environ.get("A2MC_PFLOTRAN_REFERENCE_MAS", "")

pytestmark = pytest.mark.skipif(
    not REGISTRY.is_file(), reason="output registry not generated in this clone")


def test_registry_carries_the_full_column_surface():
    data = json.loads(REGISTRY.read_text())
    assert data["n_columns"] == len(data["columns"]) == 332, (
        "the miniLEO tape has 332 columns, all unique — a different count means the "
        "registry was regenerated from a different deck")
    names = [c["name"] for c in data["columns"]]
    assert len(set(names)) == len(names), "column headers must be unique; they are the key"
    assert data["model_commit"] and data["source_deck"]


def test_registry_states_that_it_is_deck_scoped():
    """The artifact's value is destroyed by a reader who takes it as model-scoped.

    PFLOTRAN's columns are assembled at runtime from deck-defined couplers and species,
    so unlike EcoSIM's source-derived CDL this CANNOT be authoritative for the model.
    """
    data = json.loads(REGISTRY.read_text())
    warning = data.get("scope_warning", "")
    assert "DECK-SCOPED" in warning, "the registry must announce its own scope limit"
    assert data["source_deck"] in warning, (
        "the warning must name WHICH deck this surface came from — a scope caveat that "
        "does not identify the deck cannot be acted on")
    assert data["model_commit"] in warning


def test_stored_derived_fields_match_todays_parser():
    """The derived values are redundant on purpose — so drift is a visible diff."""
    from models.pflotran.output_parser import PFLOTRANOutputVariable
    data = json.loads(REGISTRY.read_text())
    for c in data["columns"]:
        ov = PFLOTRANOutputVariable(
            name=c["name"], variable=c["variable"], units=c["units"],
            scope=c["scope"], family=c["family"], column_index=c["column_index"])
        assert ov.is_rate == c["is_rate"], c["name"]
        assert ov.is_cumulative == c["is_cumulative"], c["name"]
        assert ov.dimension_level == c["dimension_level"], c["name"]
        assert ov.long_name == c["long_name"], c["name"]


def test_load_registry_recomputes_rather_than_trusting_stored_derived_values(tmp_path):
    """A stale derived value in the file must never reach a consumer."""
    data = json.loads(REGISTRY.read_text())
    data["columns"] = data["columns"][:3]
    for c in data["columns"]:                       # poison every derived field
        c["long_name"] = "WRONG"
        c["is_rate"] = not c["is_rate"]
    poisoned = tmp_path / "poisoned.json"
    poisoned.write_text(json.dumps(data))

    inv = EX.load_registry(poisoned)
    for name, ov in inv.items():
        assert ov.long_name != "WRONG", f"{name}: a stored long_name reached the consumer"


@pytest.mark.skipif(not (_TAPE and Path(_TAPE).is_file()),
                    reason="reference tape not staged (set A2MC_PFLOTRAN_REFERENCE_MAS)")
def test_registry_round_trips_the_tape_exactly():
    """The whole point: registry-derived == tape-derived, field for field."""
    from_tape = PFLOTRANOutputParser().parse(Path(_TAPE))
    from_registry = EX.load_registry(REGISTRY)

    assert set(from_registry) == set(from_tape), "column sets differ"
    for name, tape_ov in from_tape.items():
        reg_ov = from_registry[name]
        assert (reg_ov.variable, reg_ov.units, reg_ov.scope, reg_ov.family,
                reg_ov.column_index) == (tape_ov.variable, tape_ov.units, tape_ov.scope,
                                         tape_ov.family, tape_ov.column_index), name
        assert reg_ov.long_name == tape_ov.long_name, name


def test_rag_build_falls_back_to_the_registry_and_prefers_the_tape(capsys):
    """A missing tape used to drop all 332 output nodes while reporting success."""
    build = _load_script("build_pflotran_rag")

    inv = build._output_inventory(Path("/nonexistent/pflotran-mas.dat"))
    assert len(inv) == 332, "the registry fallback did not supply the output surface"
    assert "committed registry" in capsys.readouterr().out

    if _TAPE and Path(_TAPE).is_file():
        inv_tape = build._output_inventory(Path(_TAPE))
        assert len(inv_tape) == 332
        assert "committed registry" not in capsys.readouterr().out, (
            "the live tape must be preferred over the snapshot")


def test_rag_build_reports_when_neither_source_exists(capsys):
    """Silence here is what the whole fallback exists to prevent.

    An empty output inventory means a graph with zero column nodes, which is exactly
    the state that used to be reported as a successful build.
    """
    build = _load_script("build_pflotran_rag")
    inv = build._output_inventory(Path("/nonexistent/pflotran-mas.dat"),
                                  registry=Path("/nonexistent/registry.json"))
    assert inv == {}
    assert "NEITHER" in capsys.readouterr().out
