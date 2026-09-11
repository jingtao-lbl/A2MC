"""Tests for tools/read_reduced.py and the output-registry guard that feeds it.

EVERY TEST HERE IS A NEGATIVE CONTROL FOR A MISTAKE THAT ACTUALLY HAPPENED on 2026-09-08, when a
diagnostic pull applied one `nanmean` to six variables with five different temporal semantics and
read a `default='inactive'` field as gross production. A test asserting the tool merely runs would
not have caught any of it, so each case below names the error it reproduces.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from tools.read_reduced import (  # noqa: E402
    KIND_OVERRIDES, Kind, classify, reduction_for, registry,
)

MODEL, COMMIT = "ecosim", "0366560a"


@pytest.fixture(scope="module")
def reg():
    try:
        return registry(MODEL, COMMIT)
    except SystemExit as exc:
        pytest.skip(f"registry not present: {exc}")


# --------------------------------------------------------------- the five kinds are separable

@pytest.mark.parametrize("var,kind", [
    # A rate: the units carry a time denominator, so a mean is right and a sum is not.
    ("Root_CO2Relez_col", Kind.RATE),
    # avgflag='I' plus the model's own year-reset token: the annual value is at the year's END.
    # Reduced with a mean it returns roughly half its annual total and moves with the reset phase.
    ("Uptk_NMin_CumYr_FLX_pft", Kind.CUMULATIVE_YEAR),
    # avgflag='I' with no reset token: monotone. A mean reports where the run was on average
    # rather than what it accumulated.
    ("CAN_cumGPP_pft", Kind.CUMULATIVE_RUN),
    ("ECO_NPP_col", Kind.CUMULATIVE_RUN),
])
def test_kind_is_read_from_source_true_fields(reg, var, kind):
    assert classify(reg[var], MODEL) is kind


def test_increment_and_stock_are_NOT_separable_and_the_tool_says_so(reg):
    """The honest limit. `avgflag='A'` with mass units covers a per-record increment AND a stock,
    and nothing in the registry separates them, so `classify` must return AMBIGUOUS for both rather
    than pick one. This is the test that stops a future edit from adding a name heuristic."""
    assert classify(reg["NPP_pft"], MODEL) is Kind.AMBIGUOUS
    assert classify(reg["Root_N_pft"], MODEL) is Kind.AMBIGUOUS


def test_ambiguous_without_an_override_RAISES_rather_than_guessing(reg):
    """The load-bearing behaviour. A silent plausible answer is what produced the original error."""
    entry = dict(reg["NPP_pft"], name="Fabricated_Unresolved_pft")
    reg2 = dict(reg); reg2["Fabricated_Unresolved_pft"] = entry
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        reduction_for("Fabricated_Unresolved_pft", reg2, MODEL)


def test_an_override_carries_its_evidence(reg):
    """An override is a judgement, so it must not be assertable without a reason. Anything in the
    table needs prose long enough to be an argument rather than a restatement of the name."""
    for (model, var), (kind, why) in KIND_OVERRIDES.items():
        assert isinstance(kind, Kind) and kind is not Kind.AMBIGUOUS, (model, var)
        assert len(why) > 80, f"{var}: override evidence is too thin to check"


# --------------------------------------------------------------- the six original errors

def test_every_variable_i_got_wrong_now_resolves_correctly(reg):
    """The six variables from the measured incident, with the reduction each actually needs.
    `NPP_pft` as a MEAN was the headline error; it is a RATE the scorer integrates and scales by
    `step_hours`, which is why it must go through targets.yaml rather than any heuristic here."""
    # NPP_pft is deliberately NOT resolvable without targets.yaml -- see the withdrawn override.
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        reduction_for("NPP_pft", reg, MODEL)
    assert reduction_for("NPP_pft", reg, MODEL, targets={"NPP_pft": "annual"}) == "annual"
    assert reduction_for("Uptk_NMin_CumYr_FLX_pft", reg, MODEL) == "year_end"
    assert reduction_for("CAN_cumGPP_pft", reg, MODEL) == "endpoint_difference"
    assert reduction_for("Root_CO2Relez_col", reg, MODEL) == "mean"
    assert reduction_for("Root_N_pft", reg, MODEL) == "peak_or_window_mean"


def test_a_scored_variables_units_may_be_WRONG_so_the_heuristic_must_not_win(reg):
    """The registry says `NPP_pft` is `gC/m2`; `models/ecosim/backend.py:829-846` integrates it as a
    RATE, `sum(rate[year]) * step_hours` with step_hours 24, and the scorer's 422.99 against a bare
    sum's 17.62 is exactly that factor. An output variable's `units` can lie the way a parameter's
    `long_name` can, so for anything the case SCORES the target's `reduce` must win outright."""
    assert reg["NPP_pft"]["units"] == "gC/m2"          # what the registry says
    with pytest.raises(ValueError):                     # and why the heuristic must refuse it
        reduction_for("NPP_pft", reg, MODEL)


def test_the_inactive_field_is_flagged(reg, capsys):
    """`CAN_GPP_pft` is `default='inactive'` and carried the NPP values on a real tape. Reading it
    as GPP escalated into an alarm that a whole round had scored gross against a net observation."""
    assert reg["CAN_GPP_pft"]["status"] == "inactive"
    reduction_for("CAN_GPP_pft", reg, MODEL)
    assert "inactive" in capsys.readouterr().err


def test_a_scored_target_reduction_WINS_over_the_heuristic(reg):
    """A variable the case scores must be reduced the way the scorer reduces it, or a figure and
    its score disagree invisibly -- which this round has already done once, with two metrics under
    one name."""
    assert reduction_for("NPP_pft", reg, MODEL, targets={"NPP_pft": "annual"}) == "annual"


def test_an_unknown_variable_raises_instead_of_falling_back_to_the_tape(reg):
    with pytest.raises(KeyError, match="not in the output registry"):
        reduction_for("No_Such_Variable_pft", reg, MODEL)


# --------------------------------------------------------------- the registry itself

def test_the_registry_carries_avgflag_at_all(reg):
    """Before 2026-09-08 the CDL had zero `avgflag` attributes, so the temporal semantics existed
    only in `hist_addfld1d` and no consumer could reach them."""
    have = sum(1 for e in reg.values() if e.get("avgflag"))
    assert have > 500, f"only {have} of {len(reg)} entries carry avgflag"


def test_the_registry_does_not_leak_an_authoring_path():
    """Commit 0e229307 scrubbed the authoring path out of the ARTIFACT and left the GENERATOR
    emitting it, so every regeneration silently undid the scrub. These CDLs ship publicly."""
    kb = pathlib.Path(__file__).resolve().parent.parent / "docs" / "ecosim-knowledge-base"
    for cdl in kb.glob("ecosim_output_info_*.cdl"):
        head = "\n".join(cdl.read_text().splitlines()[:20])
        assert "/global/homes/" not in head and "cdirs/m5199" not in head, cdl.name
