"""
reasoning/retrieval_vocab.py — the reasoning-loop RAG query no longer asks
FATES's vocabulary of a non-FATES model's index.

Root-cause finding: memory/dev_logs_adapterkitpflotran/
20260807k_Step13_Reasoning_Half_The_Retriever_Is_Right_The_Query_Is_FATES.md.
FATES has no `models/fates/` adapter (predates adapter-kit), so "no active
adapter resolves" IS the FATES case -- these tests assert that path is
byte-identical to the pre-fix hardcoded behavior, and that an adapter model
(PFLOTRAN, EcoSIM) gets its OWN vocabulary instead.
"""
from __future__ import annotations

import models.ecosim  # noqa: F401 -- registers at import time
import models.pflotran  # noqa: F401 -- registers at import time

from reasoning.retrieval_vocab import (
    active_adapter_spec,
    domain_flavored_query,
    infer_mechanisms_from_text,
    resolve_output_names,
    retrieval_mechanisms,
)


# --- FATES path (no A2MC_MODEL / unregistered "fates") = byte-identical legacy ----

def test_no_adapter_resolves_when_a2mc_model_unset(monkeypatch):
    monkeypatch.delenv("A2MC_MODEL", raising=False)
    assert active_adapter_spec() is None


def test_no_adapter_resolves_for_unregistered_fates(monkeypatch):
    monkeypatch.setenv("A2MC_MODEL", "fates")
    assert active_adapter_spec() is None


def test_fates_output_name_mangling_unchanged(monkeypatch):
    monkeypatch.delenv("A2MC_MODEL", raising=False)
    out = resolve_output_names(
        ["outflow_Ca"], legacy_fmt=lambda t: f"FATES_{t.upper().replace('_', 'C_')}"
    )
    assert out == ["FATES_OUTFLOWC_CA"]  # exact pre-fix string


def test_fates_variable_field_still_wins_over_legacy_mangling(monkeypatch):
    # Kougarok's own targets.yaml already carries a real `variable:` field
    # (FATES_LEAFC_SZPF) -- this ALWAYS took priority once passed through, so
    # asserting it here locks in that the new priority order didn't change
    # existing correct FATES behavior for a target that already had one.
    monkeypatch.delenv("A2MC_MODEL", raising=False)
    out = resolve_output_names(
        ["PFT10_leaf"],
        targets={"PFT10_leaf": {"variable": "FATES_LEAFC_SZPF"}},
        legacy_fmt=lambda t: f"FATES_{t.upper().replace('_', 'C_')}",
    )
    assert out == ["FATES_LEAFC_SZPF"]


def test_fates_mechanisms_unchanged(monkeypatch):
    monkeypatch.delenv("A2MC_MODEL", raising=False)
    legacy = ("PID_Controller", "ECA_Competition", "Storage_Allocation")
    assert retrieval_mechanisms(legacy=legacy) == list(legacy)


def test_fates_keyword_scan_unchanged(monkeypatch):
    monkeypatch.delenv("A2MC_MODEL", raising=False)
    assert infer_mechanisms_from_text("PID oscillation and allocation drift") == ["PID_Controller"]
    assert infer_mechanisms_from_text("nitrogen and phosphorus limitation") == ["ECA_Competition"]
    assert infer_mechanisms_from_text("storage pool depleted") == ["Storage_Allocation"]
    assert infer_mechanisms_from_text("mortality spike, carbon starvation") == ["Carbon_Starvation"]
    assert infer_mechanisms_from_text("nothing relevant here") == []


def test_fates_domain_query_unchanged(monkeypatch):
    monkeypatch.delenv("A2MC_MODEL", raising=False)
    legacy = "calibration diagnosis nutrient limitation biomass allocation"
    assert domain_flavored_query("calibration diagnosis", legacy=legacy) == legacy


# --- PFLOTRAN path: real column names, no FATES-shaped guessing -------------------

def test_pflotran_output_name_identity_default(monkeypatch):
    monkeypatch.setenv("A2MC_MODEL", "pflotran")
    out = resolve_output_names(
        ["outflow_Ca"], legacy_fmt=lambda t: f"FATES_{t.upper().replace('_', 'C_')}"
    )
    assert out == ["outflow_Ca"]  # identity default, NOT FATES_OUTFLOWC_CA


def test_pflotran_variable_field_wins(monkeypatch):
    monkeypatch.setenv("A2MC_MODEL", "pflotran")
    out = resolve_output_names(
        ["outflow_Ca"],
        targets={"outflow_Ca": {"variable": "east Ca++ [mol/h]"}},
        legacy_fmt=lambda t: f"FATES_{t.upper().replace('_', 'C_')}",
    )
    assert out == ["east Ca++ [mol/h]"]


def test_pflotran_mechanisms_are_its_own(monkeypatch):
    monkeypatch.setenv("A2MC_MODEL", "pflotran")
    mechs = retrieval_mechanisms()
    assert "Mineral_Precipitation_Dissolution" in mechs
    assert "TST_Mineral_Kinetics" in mechs
    assert "PID_Controller" not in mechs  # no FATES vocabulary leaks in


def test_pflotran_keyword_scan_uses_its_own_map(monkeypatch):
    monkeypatch.setenv("A2MC_MODEL", "pflotran")
    found = infer_mechanisms_from_text("Mineral precipitation observed at the outlet")
    assert "Mineral_Precipitation_Dissolution" in found
    assert "PID_Controller" not in infer_mechanisms_from_text("PID oscillation and allocation drift")


def test_pflotran_domain_query_uses_its_own_domain(monkeypatch):
    monkeypatch.setenv("A2MC_MODEL", "pflotran")
    q = domain_flavored_query("calibration diagnosis", legacy="calibration diagnosis nutrient limitation biomass allocation")
    assert q.startswith("calibration diagnosis PFLOTRAN")
    assert "biomass allocation" not in q


# --- EcoSIM path: same contract, different vocabulary ------------------------------

def test_ecosim_output_name_identity_default(monkeypatch):
    monkeypatch.setenv("A2MC_MODEL", "ecosim")
    out = resolve_output_names(
        ["plant_C"], legacy_fmt=lambda t: f"FATES_{t.upper().replace('_', 'C_')}"
    )
    assert out == ["plant_C"]


def test_ecosim_mechanisms_are_its_own(monkeypatch):
    monkeypatch.setenv("A2MC_MODEL", "ecosim")
    mechs = retrieval_mechanisms()
    assert "Campbell_Soil_Retention" in mechs
    assert "PID_Controller" not in mechs


def test_ecosim_domain_query_uses_its_own_domain(monkeypatch):
    monkeypatch.setenv("A2MC_MODEL", "ecosim")
    q = domain_flavored_query("calibration diagnosis", legacy="calibration diagnosis nutrient limitation biomass allocation")
    assert q.startswith("calibration diagnosis EcoSIM")
