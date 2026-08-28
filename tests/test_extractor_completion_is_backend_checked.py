"""The ensemble extractors must decide completion via the BACKEND, never a tape glob.

Added 2026-08-21. v2.257 fixed `EcoSIMBackend.check_case_status` to require the final restart
rather than the mere presence of an `h0` tape -- EcoSIM opens that tape at initialisation, so a
truncated run leaves evidence identical to a complete one. Fixing the backend did NOT fix its
consumers: `scripts/extract_crossed_ensemble_targets.py` globbed the tape directly and never called
`check_case_status`, so it SCORED truncated runs and wrote them as valid Y-matrix rows. That matrix
fed the R1/R2 Morris screens.

These are source-level contract tests. The extractors are argparse scripts that walk a real run
root, so an end-to-end test would need a fixture ensemble; what is pinned here is the property that
actually regressed -- a consumer deciding completion for itself.
"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

SCORERS = [
    "scripts/extract_crossed_ensemble_targets.py",
    "scripts/extract_flat_ensemble_targets.py",
]
VIEWERS = ["scripts/extract_and_plot_adapter_ensemble.py"]

# A glob used as a COMPLETION test. Matches `.glob("*.h0.*.nc")` and the ecosim-prefixed form.
_TAPE_GLOB = re.compile(r"""\.glob\(\s*["']\*(?:\.ecosim)?\.h0\.\*\.nc["']\s*\)""")


def _code_only(src: str) -> str:
    """Source with whole-line `#` comments removed.

    The first version of these tests matched raw source and failed on the fix's own explanatory
    comments, which QUOTE the removed code so a reader understands what was wrong. A test that
    cannot tell code from a comment about code is a weak test, and the alternative -- rewording
    the comments so a grep stops matching -- would delete the explanation to satisfy the checker.
    """
    return "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))


@pytest.mark.parametrize("rel", SCORERS + VIEWERS)
def test_extractor_consults_the_backend_status_check(rel):
    """Every ensemble extractor must call check_case_status. This is the property that regressed."""
    src = (REPO / rel).read_text()
    assert "check_case_status" in src, (
        f"{rel} decides completion without the backend's check. A tape glob answers "
        f"'did the run START', not 'did it FINISH'."
    )


@pytest.mark.parametrize("rel", SCORERS)
def test_scorer_does_not_gate_on_a_tape_glob(rel):
    """A SCORER must not let a tape glob decide whether to score a case.

    Viewers are exempt: they legitimately render partial ensembles, and are covered by
    test_viewer_records_status_instead_of_claiming_completion below.
    """
    hits = _TAPE_GLOB.findall(_code_only((REPO / rel).read_text()))
    assert not hits, f"{rel} still gates on a tape glob: {hits}"


@pytest.mark.parametrize("rel", VIEWERS)
def test_viewer_records_status_instead_of_claiming_completion(rel):
    """A viewer may include started-but-unfinished cases; it may not CALL them completed."""
    code = _code_only((REPO / rel).read_text())
    assert "status_of" in code, f"{rel} does not record a per-case status"
    assert '"status"' in code, f"{rel} does not carry status into its per-case output"
    # The user-facing count must separate the two populations. The old line called every case with
    # a tape a "completed case", which is the claim that made a truncated trajectory look final.
    assert "COMPLETED" in code and "not finished" in code, (
        f"{rel} does not report completed and unfinished cases separately"
    )


def test_crossed_extractor_counts_incomplete_separately():
    """An incomplete case must be reported as its own category, not folded into 'missing'.

    Folding them together would hide the very population this fix exists to surface.
    """
    code = _code_only((REPO / "scripts/extract_crossed_ensemble_targets.py").read_text())
    assert "incomplete" in code
    assert 'status != "COMPLETED"' in code, "the COMPLETED verdict must be what gates scoring"


# --------------------------------------------------------------------------------------------
# The chunked-subprocess driver (added 2026-08-21, ported from the prior art this script
# generalizes). Its absence would manufacture FAKE failure rows at scale; see dev log 20260821f.
# --------------------------------------------------------------------------------------------

def test_flat_extractor_has_subprocess_isolation():
    """The flat extractor must isolate chunks, and must do it BY DEFAULT.

    A mitigation that is off unless requested is a mitigation nobody gets. The prior art
    (extract_morris_results.py) chunks unconditionally.
    """
    code = _code_only((REPO / "scripts/extract_flat_ensemble_targets.py").read_text())
    assert "_drive_chunked" in code, "no chunked driver"
    assert "subprocess" in code, "chunks are not run in separate processes"
    m = re.search(r'"--chunk-size",\s*type=int,\s*default=(\d+)', code)
    assert m, "no --chunk-size option"
    assert int(m.group(1)) > 0, "chunking must be ON by default"


@pytest.mark.parametrize("first,last,size,expect", [
    (0, 9, 5, [(0, 4), (5, 9)]),
    (0, 9, 10, [(0, 9)]),
    (0, 9, 100, [(0, 9)]),          # a size larger than the range is one chunk, not an error
    (1, 12, 4, [(1, 4), (5, 8), (9, 12)]),
    (7, 7, 3, [(7, 7)]),            # single case
    (0, 10, 4, [(0, 3), (4, 7), (8, 10)]),   # ragged tail
])
def test_chunk_bounds_partition_the_range(first, last, size, expect):
    from scripts.extract_flat_ensemble_targets import chunk_bounds
    assert chunk_bounds(first, last, size) == expect


@pytest.mark.parametrize("first,last,size", [(0, 9, 0), (0, 9, -1), (5, 4, 3)])
def test_chunk_bounds_rejects_nonsense(first, last, size):
    from scripts.extract_flat_ensemble_targets import chunk_bounds
    with pytest.raises(ValueError):
        chunk_bounds(first, last, size)


def test_chunk_bounds_cover_every_case_exactly_once():
    """The property that matters: a gap silently drops rows, an overlap duplicates them."""
    from scripts.extract_flat_ensemble_targets import chunk_bounds
    for size in (1, 3, 7, 50, 999):
        seen = [n for a, b in chunk_bounds(0, 1000, size) for n in range(a, b + 1)]
        assert seen == list(range(0, 1001)), f"chunk size {size} does not partition the range"


def test_a_dead_chunk_is_not_tolerated():
    """A chunk that exits non-zero must abort, not leave its cases missing from the matrix."""
    code = _code_only((REPO / "scripts/extract_flat_ensemble_targets.py").read_text())
    assert "r.returncode != 0" in code and "return 1" in code
    # and the concatenation must verify it produced a row per case
    assert "n_rows != total" in code, "no row-count guard after concatenation"
