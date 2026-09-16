"""A report's References section must not contain a work nobody opened.

The failure this guards is invisible on the page: a fabricated entry has the same shape as a real
one, and it is the single claim in a report a reader cannot check without leaving the report. The
measured instance carried a real author and year lifted from a module docstring, an invented title,
and `*Ecosystem modelling literature.*` where the venue belongs.

The checker cannot confirm a DOI resolves to the title beside it -- that needs Crossref, and
`literature-review` owns that rule for the human. It CAN demand that something resolvable is there,
which a fabricated entry has nothing to supply.

Every test below asserts a way the checker must FAIL, or a way it must not pass silently
([[feedback_a_check_that_cannot_fail]]).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.check_report_references import check, RULES_FROM, _cites_in   # noqa: E402

REAL = ("Liu, L., Zhou, W. and Jin, Z. (2024). Knowledge-guided machine learning can improve carbon "
        "cycle quantification in agroecosystems. *Nature Communications* **15**, 357. "
        "https://doi.org/10.1038/s41467-023-43860-5")
FAKE = ("Liu, L. et al. (2024). Knowledge-guided machine learning for agroecosystem carbon dynamics "
        "(KGML-ag-Carbon). *Ecosystem modelling literature.*")


def _report(tmp_path, refs, prose="Liu et al. (2024) did the thing.", day="20260916"):
    d = tmp_path / "use_cases" / "C" / "reports" / f"{day}a_topic"
    d.mkdir(parents=True)
    f = d / "report.md"
    f.write_text(f"# t\n\n## 1. Intro\n\n{prose}\n\n## 6. References\n\n{refs}\n")
    return f


def test_a_reference_with_no_identifier_is_an_error(tmp_path):
    """THE measured failure: an entry assembled rather than read has no DOI to give."""
    errs, _ = check(_report(tmp_path, FAKE), tmp_path)
    assert len(errs) == 1 and "NO resolvable identifier" in errs[0]


def test_the_same_entry_with_its_real_doi_passes(tmp_path):
    """The negative control. Without it the test above only proves the checker errors on something."""
    errs, warns = check(_report(tmp_path, REAL), tmp_path)
    assert errs == [] and warns == []


def test_a_git_revision_in_backticks_does_not_launder_a_citation(tmp_path):
    """The hole the first implementation had: the internal-artifact exemption requires a PATH.

    Written to accept any backticked token, it exempted a published book chapter whose only
    backtick was `157a26f7`. A hash is not a citation.
    """
    entry = ("Hammond, G. and Lichtner, P. (2012). PFLOTRAN: reactive flow and transport code. "
             "Revision `157a26f7` as run here.")
    errs, _ = check(_report(tmp_path, entry, prose="Hammond et al. (2012)."), tmp_path)
    assert len(errs) == 1 and "NO resolvable identifier" in errs[0]


def test_an_internal_artifact_under_references_warns_and_does_not_error(tmp_path):
    """X7. A log is real and resolvable, so it is not an X1 fabrication -- it is in the wrong section.

    The PI's rule (2026-09-16): internal artifacts belong in Cross-references or Provenance, never
    among published works. Until then this shape was silently EXEMPT, which is why the assertion is
    on the WARNING and not merely on the absence of an error: the old test passed either way.
    """
    entry = ("Tao, J. (2026). The withheld-year test. "
             "`use_cases/EcoSIM_Lusignan/memory/logs/20260913b_Withheld_Year_Test.md`.")
    errs, warns = check(_report(tmp_path, entry, prose="Tao (2026) reports it."), tmp_path)
    assert errs == []
    assert any("internal artifact listed under References" in w for w in warns)


def test_a_real_paper_that_also_carries_a_repo_path_is_still_checked(tmp_path):
    """The X7 branch must not become a way to smuggle an unidentified publication past X1.

    An entry carrying BOTH a DOI and a repo path is a published work, so it takes the X1 path.
    """
    entry = REAL + " Artifact at `use_cases/C/memory/phase_results/20260101a_stem/`."
    errs, warns = check(_report(tmp_path, entry), tmp_path)
    assert errs == [] and warns == []


def test_a_truncated_doi_is_an_error(tmp_path):
    """`doi:` introducing nothing resolves to nothing while reading as provenance."""
    entry = "Someone, A. (2020). A paper with a broken pointer. *A Journal*. doi: https://example.org/x"
    errs, _ = check(_report(tmp_path, entry, prose="Someone (2020)."), tmp_path)
    assert len(errs) == 1 and "malformed DOI" in errs[0]


def test_an_empty_references_section_is_an_error(tmp_path):
    """Worse than no section: it reads as 'sources were checked'."""
    errs, _ = check(_report(tmp_path, "\n"), tmp_path)
    assert len(errs) == 1 and "no entries" in errs[0]


def test_a_report_with_no_references_section_is_not_penalised(tmp_path):
    """Most reports cite only internal artifacts; requiring a section would make the check noise."""
    d = tmp_path / "use_cases" / "C" / "reports" / "20260916a_topic"
    d.mkdir(parents=True)
    f = d / "report.md"
    f.write_text("# t\n\n## 1. Intro\n\nNo literature here.\n")
    assert check(f, tmp_path) == ([], [])


def test_prose_citing_a_work_not_in_the_list_warns(tmp_path):
    errs, warns = check(_report(tmp_path, REAL, prose="Jeong et al. (2026) built one."), tmp_path)
    assert errs == []
    assert any("no matching References entry" in w and "Jeong" in w for w in warns)


def test_a_listed_work_no_prose_names_warns(tmp_path):
    errs, warns = check(_report(tmp_path, REAL, prose="Nothing is cited here."), tmp_path)
    assert any("no prose citation names" in w and "Liu" in w for w in warns)


def test_both_citation_styles_are_recognised(tmp_path):
    """A matcher that fires on one style reads the other as absence.

    Measured while building the checker: the narrative-only pattern reported an orphan entry AFTER
    the prose citation was added, because it was written parenthetically
    ([[feedback_exact_strings_are_contracts]]).
    """
    assert ("Hammond", "2012") in _cites_in("PFLOTRAN (Hammond et al., 2012) simulates it.")
    assert ("Hammond", "2012") in _cites_in("Hammond et al. (2012) describe it.")
    errs, warns = check(_report(tmp_path, REAL, prose="see (Liu et al., 2024) for it."), tmp_path)
    assert errs == [] and warns == []


def test_a_citation_quoted_inside_a_code_fence_is_not_the_reports_claim(tmp_path):
    d = tmp_path / "use_cases" / "C" / "reports" / "20260916a_topic"
    d.mkdir(parents=True)
    f = d / "report.md"
    f.write_text("# t\n\n## 1. Intro\n\n```\nGhost et al. (1999) is an example string.\n```\n\n"
                 f"## 6. References\n\n{REAL}\n\nLiu et al. (2024) is cited above.\n")
    _, warns = check(f, tmp_path)
    assert not any("Ghost" in w for w in warns)


def test_reports_predating_the_rule_are_grandfathered(tmp_path):
    """Retro-failing existing reports teaches people to pass --no-verify."""
    day = str(int(RULES_FROM) - 1)
    assert check(_report(tmp_path, FAKE, day=day), tmp_path) == ([], [])


def test_a_non_report_path_passed_explicitly_is_an_error(tmp_path):
    """A sweep skips a README; a path passed BY HAND is a mistake worth saying out loud."""
    f = tmp_path / "use_cases" / "C" / "reports" / "README.md"
    f.parent.mkdir(parents=True)
    f.write_text("# readme\n")
    errs, _ = check(f, tmp_path)
    assert len(errs) == 1 and "not a report path" in errs[0]
