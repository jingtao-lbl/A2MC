"""`check_calibration_log_conformance.py` — both log types the `calibration-log` skill defines.

Every check is asserted in BOTH directions: a conforming log must pass, and a specific defect must
fail. A gate that cannot fail is not a gate, and this repo shipped one earlier the same day —
`check_log_conformance.py` verified 4 of the 8 sections it claimed to
([[20260814e_Log_Spec_Gaps_Closed_And_Checker_Made_Subtype_Aware]]).

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import check_calibration_log_conformance as ccl  # noqa: E402


# --------------------------------------------------------------------------- fixtures
GOOD_PHASE = """\
# A Conforming Phase 6 Log

**Site:** EcoSIM_BioCON
**Phase:** 6 - Refinement
**Round:** 3 | **Cycle:** 1
**Date:** 2026-08-14 10:00:00

---

## Iteration Context
x

## Target Changes
x

## AI Reasoning and Deep Analysis
x

## Lessons Learned
x

## Discoveries (for gained_knowledge)
x

## Failed Approaches (DO NOT REPEAT)
x

## Experiment Results Summary
x

## Phase Handshake

**Inherited from the previous phase:** 20260814a_phase5_testing_r03_c01 — variants completed
**Handed to the next phase:** the convergence decision
**Next action:** run phase 3 diagnosis on the binding target

## Skills and memory invoked
- **Skills:** `phase6-refinement`
"""

GOOD_FREE = """\
# A Conforming Free-Form Calibration Log

**Site:** EcoSIM_BioCON
**Date:** August 14, 2026
**Author:** Jing Tao with Claude Code
**Type:** exploration

---

## What I looked at
x

## Skills and memory invoked
- **Skills:** none.

## Cross-references
- x

## Next
x
"""


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


def _codes(findings, level=None):
    return [f.code for f in findings if level is None or f.level == level]


# --------------------------------------------------------------------------- the contract source
def test_per_phase_contract_is_READ_from_phase_logger_not_copied():
    """The whole point of the ast reader: one source of truth for the per-phase sections."""
    got = ccl.load_expected_sections()
    assert set(got) == {0, 1, 2, 3, 4, 5, 6}, "did not recover every phase's section list"
    # Spot-check against the generator's own text, so a silent parse regression is caught.
    src = (REPO / "tools" / "phase_logger.py").read_text()
    for sec in got[6]:
        assert sec in src
    assert "Target Changes" in got[6] and "Morris Results" in got[1]


def test_parser_failure_is_reported_not_silently_passed(tmp_path, monkeypatch):
    """If the constant ever moves, the per-phase check must SAY it was skipped. Returning {} and
    passing everything would be the exact silent-zero failure this suite exists to prevent."""
    p = _write(tmp_path, "20260814a_phase6_refinement_r03_c01_x.md", GOOD_PHASE)
    f = ccl.check_file(p, expected_sections={})
    assert "C4" in _codes(f, "warn")


# --------------------------------------------------------------------------- TYPE A: phase logs
def test_conforming_phase_log_passes(tmp_path):
    p = _write(tmp_path, "20260814a_phase6_refinement_r03_c01_good.md", GOOD_PHASE)
    assert ccl.check_file(p) == []


@pytest.mark.parametrize("section", ["Target Changes", "Lessons Learned",
                                     "Experiment Results Summary"])
def test_C4_rejects_a_missing_per_phase_section(tmp_path, section):
    p = _write(tmp_path, "20260814a_phase6_refinement_r03_c01_x.md",
               GOOD_PHASE.replace(f"## {section}\n", "## Something Else\n"))
    assert "C4" in _codes(ccl.check_file(p), "error")


def test_C4_is_non_retroactive(tmp_path):
    """89 phase logs predate the contract; they must not be condemned for it. Applied
    retroactively this rule produced 401 errors across them."""
    p = _write(tmp_path, "20260715a_phase6_refinement_r01_c01_old.md",
               GOOD_PHASE.replace("## Target Changes\n", "## Other\n"))
    assert "C4" not in _codes(ccl.check_file(p))


def test_C4_defers_to_C7_for_generator_declared_gaps(tmp_path):
    """A section the generator already listed under 'Sections not provided' is C7's finding, not
    a second C4 error for the same gap."""
    text = GOOD_PHASE.replace("## Target Changes\nx\n", "") + (
        "\n## Sections not provided\n- Target Changes — _(not provided)_\n")
    p = _write(tmp_path, "20260814a_phase6_refinement_r03_c01_x.md", text)
    f = ccl.check_file(p)
    assert "C7" in _codes(f, "warn")
    assert not [x for x in f if x.code == "C4" and "Target Changes" in x.msg]


def test_C3_catches_a_phase_number_mismatch(tmp_path):
    p = _write(tmp_path, "20260814a_phase3_diagnosis_r03_c01_x.md", GOOD_PHASE)
    assert "C3" in _codes(ccl.check_file(p), "error")


def test_C5_requires_iteration_context(tmp_path):
    p = _write(tmp_path, "20260814a_phase6_refinement_r03_c01_x.md",
               GOOD_PHASE.replace("## Iteration Context\n", "## Nope\n"))
    assert "C5" in _codes(ccl.check_file(p), "error")


def test_C6_rejects_an_UNFILLED_handshake(tmp_path):
    """An unfilled handshake is worse than an absent one: it looks like a chain and resolves to
    nothing."""
    p = _write(tmp_path, "20260814a_phase6_refinement_r03_c01_x.md",
               GOOD_PHASE.replace("**Next action:** run phase 3 diagnosis on the binding target",
                                  "**Next action:** _(not provided — fill, or state why it "
                                  "does not apply)_"))
    assert "C6" in _codes(ccl.check_file(p), "error")


def test_C2_requires_the_phase_header_fields(tmp_path):
    p = _write(tmp_path, "20260814a_phase6_refinement_r03_c01_x.md",
               GOOD_PHASE.replace("**Site:** EcoSIM_BioCON\n", ""))
    assert "C2" in _codes(ccl.check_file(p), "error")


# --------------------------------------------------------------------------- TYPE B: free-form
def test_conforming_free_form_log_passes(tmp_path):
    p = _write(tmp_path, "20260814a_Some_Exploration.md", GOOD_FREE)
    assert ccl.check_file(p) == []


def test_free_form_is_NOT_judged_by_the_phase_contract(tmp_path):
    """The reason this tool exists alongside check_log_conformance.py: a free-form calibration log
    has no Summary/Files Changed/Verification and no Version/Branch header, and must not be failed
    for lacking them."""
    p = _write(tmp_path, "20260814a_Some_Exploration.md", GOOD_FREE)
    codes = _codes(ccl.check_file(p))
    assert "C4" not in codes and "C5" not in codes


def test_C9_requires_cross_references(tmp_path):
    p = _write(tmp_path, "20260814a_Some_Exploration.md",
               GOOD_FREE.replace("## Cross-references\n", "## Other\n"))
    assert "C9" in _codes(ccl.check_file(p), "error")


def test_C2_warns_on_a_missing_expected_header(tmp_path):
    p = _write(tmp_path, "20260814a_Some_Exploration.md",
               GOOD_FREE.replace("**Type:** exploration\n", ""))
    assert "C2" in _codes(ccl.check_file(p), "warn")


def test_C10_only_warns_on_a_missing_Next(tmp_path):
    p = _write(tmp_path, "20260814a_Some_Exploration.md",
               GOOD_FREE.replace("## Next\n", "## Other\n"))
    f = ccl.check_file(p)
    assert "C10" in _codes(f, "warn") and "C10" not in _codes(f, "error")


# --------------------------------------------------------------------------- shared + plumbing
@pytest.mark.parametrize("name,body", [("20260814a_phase6_refinement_r03_c01_x.md", GOOD_PHASE),
                                       ("20260814a_Some_Exploration.md", GOOD_FREE)])
def test_C8_capability_block_required_for_BOTH_types(tmp_path, name, body):
    p = _write(tmp_path, name, body.replace("## Skills and memory invoked\n", "## Other\n"))
    assert "C8" in _codes(ccl.check_file(p), "error")


def test_C8_is_non_retroactive(tmp_path):
    p = _write(tmp_path, "20260715a_Old_Exploration.md",
               GOOD_FREE.replace("## Skills and memory invoked\n", "## Other\n"))
    assert "C8" not in _codes(ccl.check_file(p))


def test_C8_only_warns_on_the_boundary_day(tmp_path):
    p = _write(tmp_path, f"{ccl.CAPABILITY_SECTION_SINCE}a_Boundary.md",
               GOOD_FREE.replace("## Skills and memory invoked\n", "## Other\n"))
    f = ccl.check_file(p)
    assert "C8" in _codes(f, "warn") and "C8" not in _codes(f, "error")


def test_the_style_guide_itself_is_not_treated_as_a_log(tmp_path):
    p = _write(tmp_path, "CLAUDE.md", "# not a log\n")
    assert ccl.check_file(p) == []


def test_exit_codes(tmp_path, monkeypatch, capsys):
    bad = _write(tmp_path, "20260814a_Bad.md", GOOD_FREE.replace("## Cross-references\n", "## X\n"))
    warn = _write(tmp_path, "20260814b_Warn.md", GOOD_FREE.replace("## Next\n", "## X\n"))
    good = _write(tmp_path, "20260814c_Good.md", GOOD_FREE)

    def run(p):
        monkeypatch.setattr(sys, "argv", ["check_calibration_log_conformance.py", str(p)])
        rc = ccl.main()
        capsys.readouterr()
        return rc

    assert run(bad) == 2
    assert run(warn) == 1
    assert run(good) == 0


# --------------------------------------------------------------------------- stream separation
def test_refuses_a_DEVELOPMENT_log_instead_of_silently_mischecking_it(tmp_path):
    """Before this guard the tool returned '0 errors, 1 warning' on a real dev log — a near-clean
    PASS against the wrong contract, which is more dangerous than a false failure because a pass
    is never re-examined."""
    d = tmp_path / "memory" / "dev_logs_adapterkit"
    d.mkdir(parents=True)
    p = d / "20260814a_Some_Dev_Log.md"
    p.write_text(GOOD_FREE)
    f = ccl.check_file(p)
    assert [x.code for x in f] == ["C00"]
    assert "check_log_conformance.py" in f[0].msg


def test_refuses_a_MODEL_DEV_log(tmp_path):
    d = tmp_path / "memory" / "model_logs"
    d.mkdir(parents=True)
    p = d / "20260814a_Some_Model_Log.md"
    p.write_text(GOOD_FREE)
    assert [x.code for x in ccl.check_file(p)] == ["C00"]


def test_an_ambiguous_path_is_still_checked(tmp_path):
    """The guard must fire on a POSITIVE match only — a draft in a scratch dir stays checkable."""
    p = tmp_path / "20260814a_Draft.md"
    p.write_text(GOOD_FREE)
    assert ccl.check_file(p) == []


# ---------------------------------------------------------------------------------------------
# C9 — a phase-6 log that ROUTES 6→3 must carry the rethink.
#
# THE GAP THIS CLOSES (2026-08-23). `phase6-refinement` gained a rethink protocol and
# `calibration-log` gained the logging obligation, but both were prose. Measured the same day: a
# phase-6 log that routed `rethink_6to3` contained ZERO occurrences of "Rethink" and passed this
# checker clean. The next cycle reads the LOG, not the state enum, so a rethink recorded nowhere is
# a cycle that starts blind — and three consecutive rethinks in one round then carried the same base
# and the same target framing forward unexamined.

_R6 = """# A Phase 6 Log That Rethinks

**Site:** EcoSIM_BioCON
**Phase:** 6 - Refinement
**Round:** 3 | **Cycle:** 9
**Date:** 2026-09-01 10:00:00

---

## Iteration Context
x

## Target Changes
x

## AI Reasoning and Deep Analysis
x

## Lessons Learned
x

## Discoveries (for gained_knowledge)
x

## Failed Approaches (DO NOT REPEAT)
x

## Experiment Results Summary
x

{RETHINK}## Next Action: iterate

## Skills and memory invoked
- **Skills:** none
"""

_FAT = ("## The Rethink (6->3)\n\n" + ("word " * 70) +
        "\n\nPathway P1: the retention class, falsified if the target does not respond.\n\n")


def _c9(findings):
    return [f for f in findings if f.code == "C9"]


def test_C9_rejects_a_rethink_log_with_no_rethink_section(tmp_path):
    p = _write(tmp_path, "20260901a_phase6_refinement_r03_c09_x.md", _R6.format(RETHINK=""))
    f = _c9(ccl.check_file(p))
    assert f and f[0].level == "error", f


def test_C9_accepts_a_rethink_section_that_names_a_pathway(tmp_path):
    p = _write(tmp_path, "20260901b_phase6_refinement_r03_c09_x.md", _R6.format(RETHINK=_FAT))
    assert _c9(ccl.check_file(p)) == []


def test_C9_warns_on_a_present_but_hollow_rethink_section(tmp_path):
    p = _write(tmp_path, "20260901c_phase6_refinement_r03_c09_x.md",
               _R6.format(RETHINK="## The Rethink (6->3)\n\nTBD.\n\n"))
    f = _c9(ccl.check_file(p))
    assert f and f[0].level == "warn" and "thin" in f[0].msg, f


def test_C9_warns_when_the_section_names_no_pathway(tmp_path):
    """The deliverable is PATHWAYS handed to Phase 3, not a narrative of the cycle."""
    p = _write(tmp_path, "20260901d_phase6_refinement_r03_c09_x.md",
               _R6.format(RETHINK="## The Rethink (6->3)\n\n" + ("word " * 80) + "\n\n"))
    f = _c9(ccl.check_file(p))
    assert f and f[0].level == "warn" and "PATHWAY" in f[0].msg, f


def test_C9_is_silent_when_the_phase_6_log_does_NOT_route_a_rethink(tmp_path):
    """A converged or redesigning cycle owes no rethink; the check keys on the ROUTE."""
    body = _R6.format(RETHINK="").replace("## Next Action: iterate", "## Next Action: converged")
    p = _write(tmp_path, "20260901e_phase6_refinement_r03_c09_x.md", body)
    assert _c9(ccl.check_file(p)) == []


def test_C9_is_non_retroactive(tmp_path):
    """Logs predating the rule stay exempt — a permanently-red check is one nobody reads."""
    body = _R6.format(RETHINK="").replace("2026-09-01 10:00:00", "2026-08-01 10:00:00")
    p = _write(tmp_path, "20260801a_phase6_refinement_r03_c09_x.md", body)
    assert _c9(ccl.check_file(p)) == []


def test_C9_softens_to_a_warning_on_the_boundary_day(tmp_path):
    body = _R6.format(RETHINK="").replace("2026-09-01 10:00:00", "2026-08-23 10:00:00")
    p = _write(tmp_path, "20260823z_phase6_refinement_r03_c09_x.md", body)
    f = _c9(ccl.check_file(p))
    assert f and f[0].level == "warn", f
