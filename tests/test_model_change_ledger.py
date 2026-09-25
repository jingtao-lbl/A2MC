"""Negative tests for `tools/check_model_change_ledger.py`.

The ledger row is a DERIVED fact: `summarize-calibration-round` copies a change's commit, branch
and V0 result out of a model-evolution record into `config/calibration_rounds.yaml`, and both
`summarize-calibration-round` and `compare-calibration-rounds` read the copy at every round close.
A copy nothing checks drifts silently, and two artifacts disagreeing is one missing derivation.

SCOPE, deliberately narrow (PI, 2026-09-24: "no need to check old logs"). Only pointers into a
case's own `memory/model_evolution/` are checked. An entry with no `model_log`, or one pointing
into the RETIRED repo-root `memory/model_logs/` archive, is skipped -- those record changes made
before the stream moved under the case, and chasing them is not what this exists for.

Run:  ~/a2mc_env/bin/python -m pytest tests/test_model_change_ledger.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import check_model_change_ledger as mcl  # noqa: E402


RECORD = """\
# A Record

**Date:** September 24, 2026
**Author:** Jing Tao with Claude on Perlmutter
**Round:** R3

---

## Summary

The cap was promoted, on `exp/the-branch` @ `3dd8a820`.
"""

LEDGER = """\
model_change_ledger:
  anchor:
    model: ecosim
  changes:
    - id: the-change
      commit: '3dd8a820'
      branch: exp/the-branch
      title: A change
      model_log: memory/model_evolution/20260924a_model_evolution_r03_a_record.md
"""


def _case(tmp_path: Path, ledger: str = LEDGER, record: str | None = RECORD) -> Path:
    """A minimal use_cases/<Case>/ with a ledger and (optionally) the record it names."""
    case = tmp_path / "use_cases" / "EcoSIM_Test"
    (case / "config").mkdir(parents=True)
    (case / "config" / "calibration_rounds.yaml").write_text(ledger)
    d = case / "memory" / "model_evolution"
    d.mkdir(parents=True)
    if record is not None:
        (d / "20260924a_model_evolution_r03_a_record.md").write_text(record)
    return case


# --------------------------------------------------------------------------- baseline

def test_a_matching_pair_passes(tmp_path):
    assert mcl.check_case(_case(tmp_path)) == []


def test_a_repo_relative_pointer_also_resolves(tmp_path):
    """Both bases are accepted: a record lives under the case, the retired archive at the root."""
    case = _case(tmp_path, ledger=LEDGER.replace(
        "memory/model_evolution/", "use_cases/EcoSIM_Test/memory/model_evolution/"))
    assert [f for f in mcl.check_case(case, repo=tmp_path) if f.code == "G1"] == []


# --------------------------------------------------------------------------- G1 the pointer

def test_G1_a_pointer_that_resolves_to_nothing_is_an_ERROR(tmp_path):
    case = _case(tmp_path, record=None)
    fs = mcl.check_case(case)
    assert any(f.code == "G1" and f.level == "error" for f in fs), [str(f) for f in fs]


def test_G1_a_BARE_DIRECTORY_is_an_ERROR_not_a_pass(tmp_path):
    """`exists()` is true for a directory. A link checker written with it reports these clean --
    the failure mode inside the check built to close this gap."""
    case = _case(tmp_path, ledger=LEDGER.replace(
        "memory/model_evolution/20260924a_model_evolution_r03_a_record.md",
        "memory/model_evolution/"))
    fs = mcl.check_case(case)
    assert any(f.code == "G1" and f.level == "error" for f in fs), [str(f) for f in fs]


# --------------------------------------------------------------------------- G2 the content

def test_G2_a_commit_the_record_does_not_carry_is_an_ERROR(tmp_path):
    """The whole point: the ledger's COPY must still match its source."""
    case = _case(tmp_path, ledger=LEDGER.replace("'3dd8a820'", "'deadbee'"))
    fs = mcl.check_case(case)
    assert any(f.code == "G2" and f.level == "error" for f in fs), [str(f) for f in fs]


# --------------------------------------------------------------------------- G3 the reverse

def test_G3_a_record_no_entry_names_WARNS(tmp_path):
    case = _case(tmp_path)
    (case / "memory" / "model_evolution"
     / "20260924b_model_evolution_r03_unledgered.md").write_text(RECORD)
    fs = mcl.check_case(case)
    assert any(f.code == "G3" for f in fs), [str(f) for f in fs]
    assert not [f for f in fs if f.level == "error"], [str(f) for f in fs]


def test_G3_ignores_the_README(tmp_path):
    case = _case(tmp_path)
    (case / "memory" / "model_evolution" / "README.md").write_text("# not a record\n")
    assert [f for f in mcl.check_case(case) if f.code == "G3"] == []


# --------------------------------------------------------------------------- out of scope

@pytest.mark.parametrize("value,why", [
    ("memory/model_logs/20260807a_Something.md", "the RETIRED repo-root archive"),
    ("memory/model_logs/", "a bare pointer into the retired archive"),
])
def test_a_retired_stream_pointer_is_SKIPPED_not_checked(tmp_path, value, why):
    """PI, 2026-09-24: no need to check old logs."""
    case = _case(tmp_path, ledger=LEDGER.replace(
        "memory/model_evolution/20260924a_model_evolution_r03_a_record.md", value))
    assert [f for f in mcl.check_case(case) if f.code in ("G1", "G2")] == [], why


def test_an_entry_with_no_model_log_is_SKIPPED(tmp_path):
    case = _case(tmp_path, ledger="\n".join(
        l for l in LEDGER.splitlines() if "model_log:" not in l) + "\n")
    assert [f for f in mcl.check_case(case) if f.code in ("G1", "G2")] == []


def test_a_case_with_no_ledger_is_not_an_error(tmp_path):
    case = tmp_path / "use_cases" / "EcoSIM_Bare"
    (case / "config").mkdir(parents=True)
    (case / "config" / "calibration_rounds.yaml").write_text("rounds: []\n")
    assert mcl.check_case(case) == []


# --------------------------------------------------------------------------- non-retroactive

def test_a_PRE_CONTRACT_row_with_a_wrong_commit_is_exempt(tmp_path):
    """PI, 2026-09-24: a row copied before the link was checked is history, not a defect anyone
    is about to act on. Same date-scoping as check_model_evolution_conformance."""
    case = _case(tmp_path,
                 ledger=LEDGER.replace("'3dd8a820'", "'deadbee'")
                              .replace("20260924a_model_evolution", "20260905a_model_evolution"),
                 record=None)
    (case / "memory" / "model_evolution"
     / "20260905a_model_evolution_r03_a_record.md").write_text(RECORD)
    fs = mcl.check_case(case)
    assert not [f for f in fs if f.level == "error"], [str(f) for f in fs]
    assert any(f.code == "G9" for f in fs), "the exemption must be COUNTED, not silent"


def test_the_exemption_does_not_swallow_a_POST_contract_drift(tmp_path):
    """The control. Without this the exemption could be swallowing everything."""
    case = _case(tmp_path, ledger=LEDGER.replace("'3dd8a820'", "'deadbee'"))
    assert any(f.code == "G2" and f.level == "error" for f in mcl.check_case(case))


def test_a_PRE_CONTRACT_record_with_no_row_is_exempt(tmp_path):
    case = _case(tmp_path)
    (case / "memory" / "model_evolution"
     / "20260824b_model_evolution_r03_old_unledgered.md").write_text(RECORD)
    assert [f for f in mcl.check_case(case) if f.code == "G3"] == []
