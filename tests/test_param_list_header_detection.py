"""`_detect_header_row` must not mistake a prose comment for the header row.

The bare-token fallback accepts 'lower' and 'upper' as whitespace-separated words, so a comment
containing both matches as a header. Incident and measurements:
`memory/dev_logs_adapterkit/20260912j_The_Header_Detector_Matched_A_Comment.md`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from create_adapter_parameter_sample import _detect_header_row, parse_pft_param_list  # noqa: E402

LUSIGNAN = REPO / "use_cases/EcoSIM_Lusignan/parameters/ecosim_lusignan_param_list.csv"


def _tracked_param_lists() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True).stdout
    return sorted({REPO / f for f in out.split()
                   if f.endswith(".csv") and "param_list" in f})


def test_no_tracked_param_list_resolves_its_header_to_a_comment():
    """The general invariant. A comment is never a header, for any list in the repo."""
    misdetected = []
    for p in _tracked_param_lists():
        if not p.is_file():
            continue
        try:
            idx = _detect_header_row(p)
        except ValueError:
            continue                      # no bound columns at all is a different question
        if p.read_text().splitlines()[idx].lstrip().startswith("#"):
            misdetected.append(f"{p.name}: line {idx + 1}")
    assert not misdetected, (
        "these param lists resolve their header row to a COMMENT line, so pandas will read the "
        f"remaining preamble as data: {misdetected}")


@pytest.mark.skipif(not LUSIGNAN.is_file(), reason="EcoSIM_Lusignan param list not in this checkout")
def test_the_lusignan_list_parses_and_lands_on_its_real_header():
    """The specific regression, pinned so it names itself rather than joining a list."""
    idx = _detect_header_row(LUSIGNAN)
    header = LUSIGNAN.read_text().splitlines()[idx]
    assert header.startswith("name,"), (
        f"header resolved to line {idx + 1}: {header[:70]!r}. The comment eight lines above the "
        f"real header contains the bare tokens 'lower' and 'upper' between slashes.")
    names, lo, hi = parse_pft_param_list(LUSIGNAN)
    assert len(names) == 54, f"expected the round's 54 parameters, parsed {len(names)}"
    assert (lo < hi).all(), "every parameter must have lower < upper"


def test_a_prose_comment_containing_lower_and_upper_is_skipped(tmp_path):
    """The mechanism, on a minimal fixture, so the guard is exercised without the real file.

    Written to FAIL if the comment skip is removed: without it the detector returns line 0.
    """
    f = tmp_path / "list.csv"
    f.write_text(
        "# requires only name / lower / upper / default\n"
        "name,pft,default,lower_bound,upper_bound\n"
        "AAA,1,2.0,1.0,3.0\n"
        "BBB,-,5.0,4.0,6.0\n"
    )
    assert _detect_header_row(f) == 1
    names, lo, hi = parse_pft_param_list(f)
    assert names == ["AAA_1", "BBB"]
