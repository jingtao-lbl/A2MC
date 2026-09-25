"""Negative tests for `tools/check_model_evolution_conformance.py`.

A checker you have only ever watched PASS is not a verified checker. So every rule M1-M5 gets a
case that must FAIL, alongside the conforming baseline that must pass, and the two stream-refusal
directions get one each.

The contract this pins: a model-evolution record carries `## Skills and memory invoked` and that
section names `model-evolution`, because writing one means invoking that skill. Records written
before the rule took effect are exempt, which is the same non-retroactive shape the sibling
checkers use. Why each rule is the one worth having, and what the six pre-rule records actually
agreed on, is in
`memory/dev_logs_adapterkit/20260924e_The_Model_Evolution_Stream_Gets_The_Checker_It_Was_Missing.md`.

Run:  ~/a2mc_env/bin/python -m pytest tests/test_model_evolution_conformance.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import check_model_evolution_conformance as mec  # noqa: E402
import check_log_conformance as clc  # noqa: E402


GOOD = """\
# The SPOSC Hydrolysis Cap, Traced Through EcoSIM

**Date:** September 24, 2026
**Author:** Jing Tao with Claude on Perlmutter
**Type:** Model evolution
**Round:** R3
**Model:** EcoSIM, anchor `a2mc-anchor-fe075014` @ `fe075014`
**Branch in force:** `exp/no-underflow-trap` @ `3dd8a820`

---

## Summary

x

## Why this record exists

x

## Files Changed

| File | Change |
|---|---|
| `nitro.f` | capped hydrolysis, `!Jing Tao:` annotated |

## Verification

**V0-at-equality:** PASS — outputs bit-identical, and the two arms are provably different
executables: OFF `8ac0935c`, ON `c9a0b3a0`.

## Skills and memory invoked

- **Skills:** `model-evolution`
- **Memory:** `feedback_model_code_comment_jing_tao`

## Cross-references

- x
"""

STEM = "20260924a_model_evolution_r03_the_sposc_cap.md"


def _write(tmp_path: Path, name: str = STEM, text: str = GOOD) -> Path:
    """Place a record at a real model_evolution path, since detection is path-aware."""
    d = tmp_path / "use_cases" / "EcoSIM_BioCON" / "memory" / "model_evolution"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(text)
    return p


# --------------------------------------------------------------------------- baseline

def test_a_conforming_record_passes(tmp_path):
    assert mec.check_file(_write(tmp_path)) == []


# --------------------------------------------------------------------------- M1 filename

@pytest.mark.parametrize("bad", [
    "20260924a_The_Sposc_Cap.md",                    # dev-log stem, not this stream's
    "20260924a_model_evolution_the_sposc_cap.md",    # no round
    "20260924a_model_evolution_r3_the_sposc_cap.md", # round not zero-padded
    "model_evolution_r03_the_sposc_cap.md",          # no date
    "20260932a_model_evolution_r03_x.md",            # day 32 -- eight digits is not a date
])
def test_M1_a_bad_stem_fails(tmp_path, bad):
    codes = [f.code for f in mec.check_file(_write(tmp_path, name=bad))]
    assert "M1" in codes, f"{bad} should have been rejected, got {codes}"


# --------------------------------------------------------------------------- M2 header

@pytest.mark.parametrize("field", ["Date", "Author", "Round"])
def test_M2_a_missing_header_field_fails(tmp_path, field):
    text = "\n".join(l for l in GOOD.splitlines() if not l.startswith(f"**{field}:**"))
    codes = [f.code for f in mec.check_file(_write(tmp_path, text=text))]
    assert "M2" in codes, f"missing **{field}:** should have been caught, got {codes}"


# --------------------------------------------------------------------------- M3 the PI's rule

def test_M3_a_missing_skills_section_is_an_ERROR(tmp_path):
    text = GOOD.replace("## Skills and memory invoked", "## Some Other Heading")
    fs = mec.check_file(_write(tmp_path, text=text))
    assert any(f.code == "M3" and f.level == "error" for f in fs), [str(f) for f in fs]


def test_M4_the_section_must_name_model_evolution(tmp_path):
    """Writing one of these means invoking `model-evolution`."""
    text = GOOD.replace("`model-evolution`", "`calibration-log`")
    fs = mec.check_file(_write(tmp_path, text=text))
    assert any(f.code == "M4" and f.level == "error" for f in fs), [str(f) for f in fs]


def test_M4_passes_when_model_evolution_is_named_among_others(tmp_path):
    text = GOOD.replace("- **Skills:** `model-evolution`",
                        "- **Skills:** `model-evolution`, `plotting`")
    assert [f for f in mec.check_file(_write(tmp_path, text=text)) if f.code == "M4"] == []


# --------------------------------------------------------------------------- M5 warnings

def test_M5_a_missing_cross_references_WARNS_but_does_not_error(tmp_path):
    text = GOOD.replace("## Cross-references", "## Elsewhere")
    fs = mec.check_file(_write(tmp_path, text=text))
    assert any(f.code == "M5" for f in fs)
    assert not [f for f in fs if f.level == "error"], [str(f) for f in fs]


def test_M6_no_commit_identifier_WARNS(tmp_path):
    """The round's `model_change_ledger` copies a commit out of this record.

    Uses the V0 not-applicable escape, because a record with NO hash anywhere is by construction
    one that ran no V0 -- the two rules would otherwise be untestable independently."""
    text = (GOOD.replace(" @ `fe075014`", "").replace(" @ `3dd8a820`", "")
                .replace("**V0-at-equality:** PASS — outputs bit-identical, and the two arms are provably different\n"
                         "executables: OFF `8ac0935c`, ON `c9a0b3a0`.",
                         "**V0-at-equality:** not applicable — activation record, no source authored."))
    fs = mec.check_file(_write(tmp_path, text=text))
    assert any(f.code == "M6" for f in fs)
    assert not [f for f in fs if f.level == "error"], [str(f) for f in fs]


# --------------------------------------------------------------------------- non-retroactive

def test_a_record_predating_the_rule_is_exempt(tmp_path):
    """Existing records predate the contract and are exempt by design."""
    text = GOOD.replace("## Skills and memory invoked", "## Some Other Heading")
    old = _write(tmp_path, name="20260824a_model_evolution_r03_the_binary.md", text=text)
    assert mec.check_file(old) == []


def test_the_exemption_does_not_swallow_a_record_written_after_the_rule(tmp_path):
    """The control for the test above: same defect, a date on the rule's own day, must fail."""
    text = GOOD.replace("## Skills and memory invoked", "## Some Other Heading")
    new = _write(tmp_path, name="20260924b_model_evolution_r03_the_binary.md", text=text)
    assert [f.code for f in mec.check_file(new)] != []


# --------------------------------------------------------------------------- stream refusal

def test_this_tool_refuses_a_dev_log(tmp_path):
    d = tmp_path / "memory" / "dev_logs_adapterkit"
    d.mkdir(parents=True)
    p = d / "20260924a_A_Dev_Log.md"
    p.write_text(GOOD)
    fs = mec.check_file(p)
    assert any("wrong tool" in f.msg for f in fs), [str(f) for f in fs]


def test_this_tool_refuses_a_calibration_log(tmp_path):
    d = tmp_path / "use_cases" / "EcoSIM_BioCON" / "memory" / "logs"
    d.mkdir(parents=True)
    p = d / "20260924a_phase6_refinement_r03_c02_x.md"
    p.write_text(GOOD)
    fs = mec.check_file(p)
    assert any("wrong tool" in f.msg for f in fs), [str(f) for f in fs]


def test_check_log_conformance_refuses_a_model_evolution_record(tmp_path):
    """The reciprocal. Before this change it produced 5 errors demanding dev-log sections,
    which reads as "your record is broken" when the truth is "wrong tool"."""
    p = _write(tmp_path)
    fs = clc.check_file(p)
    assert any("wrong tool" in f.msg for f in fs), [str(f) for f in fs]
    assert len(fs) == 1, f"a refusal should be the ONLY finding, got {[str(f) for f in fs]}"


# --------------------------------------------------------------------------- M7-M9 PI, 2026-09-24

@pytest.mark.parametrize("section,code", [
    ("Summary", "M7"),
    ("Files Changed", "M8"),
    ("Verification", "M9"),
])
def test_a_missing_required_section_is_an_ERROR(tmp_path, section, code):
    text = GOOD.replace(f"## {section}", "## Some Other Heading")
    fs = mec.check_file(_write(tmp_path, text=text))
    assert any(f.code == code and f.level == "error" for f in fs), [str(f) for f in fs]


# --------------------------------------------------------------------------- M10 V0 evidence

def test_M10_no_V0_statement_at_all_is_an_ERROR(tmp_path):
    text = GOOD.replace("**V0-at-equality:** PASS", "**Result:** looked fine")
    fs = mec.check_file(_write(tmp_path, text=text))
    assert any(f.code == "M10" and f.level == "error" for f in fs), [str(f) for f in fs]


def test_M10_a_V0_claim_with_only_ONE_hash_is_an_ERROR(tmp_path):
    """The skill's conjunction: identical outputs alone is not evidence, because running the
    same binary twice also produces identical outputs. Two arms, provably different."""
    text = GOOD.replace("OFF `8ac0935c`, ON `c9a0b3a0`", "both arms `8ac0935c`")
    fs = mec.check_file(_write(tmp_path, text=text))
    assert any(f.code == "M10" and f.level == "error" for f in fs), [str(f) for f in fs]


def test_M10_two_IDENTICAL_hashes_do_not_satisfy_it(tmp_path):
    """Same binary twice is the specific harness error V0 cannot distinguish from a pass."""
    text = GOOD.replace("ON `c9a0b3a0`", "ON `8ac0935c`")
    fs = mec.check_file(_write(tmp_path, text=text))
    assert any(f.code == "M10" and f.level == "error" for f in fs), [str(f) for f in fs]


def test_M10_an_explicit_not_applicable_with_a_reason_passes(tmp_path):
    """An activation or build-provenance record authors no source and has no V0 to run."""
    text = GOOD.replace(
        "**V0-at-equality:** PASS — outputs bit-identical, and the two arms are provably different\n"
        "executables: OFF `8ac0935c`, ON `c9a0b3a0`.",
        "**V0-at-equality:** not applicable — activation record, no source authored and no binary built.")
    assert [f for f in mec.check_file(_write(tmp_path, text=text)) if f.code == "M10"] == []


def test_M10_not_applicable_WITHOUT_a_reason_is_an_ERROR(tmp_path):
    """The escape is a declaration, not a way to say nothing."""
    text = GOOD.replace(
        "**V0-at-equality:** PASS — outputs bit-identical, and the two arms are provably different\n"
        "executables: OFF `8ac0935c`, ON `c9a0b3a0`.",
        "**V0-at-equality:** n/a")
    fs = mec.check_file(_write(tmp_path, text=text))
    assert any(f.code == "M10" and f.level == "error" for f in fs), [str(f) for f in fs]


# --------------------------------------------------------------------------- M11 the source comment

def test_M11_no_Jing_Tao_annotation_WARNS(tmp_path):
    text = GOOD.replace(", `!Jing Tao:` annotated", "")
    fs = mec.check_file(_write(tmp_path, text=text))
    assert any(f.code == "M11" for f in fs)
    assert not [f for f in fs if f.level == "error"], [str(f) for f in fs]
