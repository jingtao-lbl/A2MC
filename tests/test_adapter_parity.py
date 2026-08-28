"""Tests for tools/validate_adapter_parity.py — the spec-parity gate.

The gate's whole value is that it FAILS on a silently-empty spec field, so these tests
lead with the failing cases. A parity check that only ever passes would be exactly the
defect it was written to catch: `model_check_input_compat` printing "nothing to check"
and reading as a pass (memory/dev_logs_adapterkitats/20260801k).

Synthetic specs are used for the check semantics so the tests do not move every time a
real adapter is filled in. Two assertions DO run against the live specs, because they
encode invariants that must hold for real: no adapter may declare a field that does not
exist, and a declaration must not outlive the field being populated.
"""
from dataclasses import fields

import pytest

from models.base import ModelSpec
from tools.validate_adapter_parity import (
    BLANKET,
    analyze,
    discover_specs,
    parity_fields,
)


def _spec(name, **kw):
    """A minimal ModelSpec with the three mandatory identity fields filled."""
    return ModelSpec(
        name=name,
        display_name=name.upper(),
        param_name_regex=r"^\w+$",
        **kw,
    )


def _run(specs):
    """analyze() over a {name: spec} map, returning (findings, excused, blanket_hits)."""
    pf = parity_fields()
    _, findings, excused, blanket_hits, _ = analyze(specs, pf)
    return findings, excused, blanket_hits


def _codes(findings, model):
    return {(c, f) for c, f, _ in findings[model]}


# =============================================================================
# Which fields participate
# =============================================================================

def test_parity_fields_only_covers_fields_whose_default_is_empty():
    """A field with a real default is never observably "empty", so it carries no parity
    signal and must not be compared — otherwise an adapter that legitimately keeps the
    default (FATES-shaped Fortran routine patterns) would be flagged forever."""
    pf = parity_fields()
    assert "hist_activate" in pf                # default () — participates
    assert "input_reader_sources" in pf
    assert "source_extensions" not in pf        # default (".F90", ".f90")
    assert "routine_decl_patterns" not in pf
    assert "module_file_pattern" not in pf
    assert "grouping_axis" not in pf            # default "pft"
    assert "milestone_label_format" not in pf   # default "{label}"


def test_parity_fields_excludes_mandatory_and_the_declaration_field_itself():
    pf = parity_fields()
    for mandatory in ("name", "display_name", "param_name_regex"):
        assert mandatory not in pf
    assert "spec_na" not in pf


def test_parity_field_set_is_derived_not_hardcoded():
    """The set must come from the dataclass, so a field added to ModelSpec later is
    compared automatically rather than silently escaping the gate."""
    declared = {f.name for f in fields(ModelSpec)}
    assert set(parity_fields()) <= declared


# =============================================================================
# P1 — the undeclared gap (the check that matters)
# =============================================================================

def test_p1_flags_a_field_a_sibling_populates_and_this_adapter_leaves_empty():
    specs = {
        "alpha": _spec("alpha", hist_activate=("VAR_A",)),
        "beta": _spec("beta"),
    }
    findings, _, _ = _run(specs)
    assert ("P1", "hist_activate") in _codes(findings, "beta")
    assert findings["alpha"] == []


def test_p1_names_the_peers_so_the_reader_knows_where_to_look():
    specs = {
        "alpha": _spec("alpha", hist_activate=("VAR_A",)),
        "gamma": _spec("gamma", hist_activate=("VAR_G",)),
        "beta": _spec("beta"),
    }
    findings, _, _ = _run(specs)
    detail = [d for c, f, d in findings["beta"] if f == "hist_activate"][0]
    assert "alpha" in detail and "gamma" in detail


def test_a_field_no_adapter_populates_is_not_a_convention_and_is_not_flagged():
    """Parity means "a convention some adapter established". A field nobody uses is not
    one, and flagging it would make the gate noise from the day ModelSpec grows."""
    specs = {"alpha": _spec("alpha"), "beta": _spec("beta")}
    findings, _, _ = _run(specs)
    assert findings["alpha"] == []
    assert findings["beta"] == []


def test_a_declared_gap_passes_and_is_still_reported():
    """Declaring must silence the FAILURE without hiding the FACT — an N/A that
    disappears from the report is indistinguishable from a field nobody thought about."""
    specs = {
        "alpha": _spec("alpha", hist_activate=("VAR_A",)),
        "beta": _spec("beta", spec_na={"hist_activate": "no history tape"}),
    }
    findings, excused, _ = _run(specs)
    assert findings["beta"] == []
    assert [f for f, _ in excused["beta"]] == ["hist_activate"]


# =============================================================================
# P2 / P3 — declarations that have gone wrong
# =============================================================================

def test_p2_flags_a_declaration_that_the_field_being_populated_has_overtaken():
    """A stale N/A is worse than none: it documents a decision that is no longer true,
    and the next reader has no reason to re-derive it."""
    specs = {
        "alpha": _spec("alpha", hist_activate=("VAR_A",)),
        "beta": _spec("beta", hist_activate=("VAR_B",),
                      spec_na={"hist_activate": "no history tape"}),
    }
    findings, _, _ = _run(specs)
    assert ("P2", "hist_activate") in _codes(findings, "beta")


def test_p3_flags_a_declaration_naming_something_that_is_not_a_spec_field():
    """A typo'd key silences nothing — including the gap it was meant to excuse — so it
    must not be able to sit in a spec looking like a decision."""
    specs = {
        "alpha": _spec("alpha", hist_activate=("VAR_A",)),
        "beta": _spec("beta", spec_na={"hist_activat": "typo"}),
    }
    findings, _, _ = _run(specs)
    assert ("P3", "hist_activat") in _codes(findings, "beta")
    # and the real gap is still open, because the typo excused nothing
    assert ("P1", "hist_activate") in _codes(findings, "beta")


# =============================================================================
# Blanket declaration (an adapter mid-onboarding)
# =============================================================================

def test_blanket_excuses_every_gap_but_lists_each_one():
    specs = {
        "alpha": _spec("alpha", hist_activate=("VAR_A",), run_length_control_label="steps"),
        "beta": _spec("beta", spec_na={BLANKET: "onboarding in progress"}),
    }
    findings, _, blanket_hits = _run(specs)
    assert findings["beta"] == []
    assert set(blanket_hits["beta"]) == {"hist_activate", "run_length_control_label"}


def test_a_specific_declaration_wins_over_the_blanket():
    """So an adapter can retire its blanket field by field without losing the reason."""
    specs = {
        "alpha": _spec("alpha", hist_activate=("VAR_A",), run_length_control_label="steps"),
        "beta": _spec("beta", spec_na={BLANKET: "onboarding",
                                       "hist_activate": "no history tape"}),
    }
    findings, excused, blanket_hits = _run(specs)
    assert [f for f, _ in excused["beta"]] == ["hist_activate"]
    assert blanket_hits["beta"] == ["run_length_control_label"]
    assert findings["beta"] == []


# =============================================================================
# Live specs — invariants that must hold for the real adapters
# =============================================================================

def test_no_live_adapter_declares_a_field_that_does_not_exist():
    valid = {f.name for f in fields(ModelSpec)} | {BLANKET}
    for name, spec in discover_specs(include_template=True).items():
        bogus = [k for k in (spec.spec_na or {}) if k not in valid]
        assert not bogus, f"{name} declares non-existent spec field(s): {bogus}"


def test_no_live_adapter_carries_a_stale_declaration():
    """P2 against the real specs: when a field gets populated, its N/A must be removed."""
    specs = discover_specs(include_template=True)
    findings, _, _ = _run(specs)
    stale = {m: [f for c, f, _ in rows if c == "P2"] for m, rows in findings.items()}
    stale = {m: f for m, f in stale.items() if f}
    assert not stale, f"stale spec_na declarations: {stale}"


@pytest.mark.parametrize("model", ["ats", "ecosim", "pflotran"])
def test_live_adapters_are_parity_clean(model):
    """Every adapter's gaps are declared. ATS was briefly excluded here on the reading that
    three of its gaps were "real defects"; that overstated it (20260801k's correction banner)
    — the rationales already existed in prose comments, and converting them to machine-readable
    declarations IS the fix, not a way around it."""
    specs = discover_specs(include_template=False)
    findings, _, _ = _run(specs)
    assert findings[model] == [], f"{model} has undeclared spec gaps: {findings[model]}"


def test_every_live_declaration_states_an_expiry_condition():
    """A rationale that was right at v0.1 and silently stopped being right is the failure this
    whole mechanism exists to catch — ATS's `hist_activate` comment was correct for the
    deck-as-registry design and is falsified by the outputs repair. A declaration must therefore
    say what would make it false. Blanket ("*") entries are exempt: they are explicitly temporary
    and the validator already prints every field they excuse.

    The marker is the literal token EXPIRES, not a fuzzy match on prose. A declaration that
    delegates to a sibling field still writes "EXPIRES: same condition as <field>" — an earlier
    version accepted a loose "same as" and let a real gap through, which is the same class of
    hole as the thing being guarded."""
    missing = []
    for name, spec in discover_specs(include_template=False).items():
        for field_name, reason in (spec.spec_na or {}).items():
            if field_name == BLANKET:
                continue
            if "EXPIRES" not in reason.upper():
                missing.append(f"{name}.{field_name}")
    assert not missing, (
        "spec_na declarations with no expiry condition (add 'EXPIRES IF/AT …'): " + ", ".join(missing))
