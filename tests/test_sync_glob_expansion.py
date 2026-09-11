"""A sync leg's glob expander must emit entries the copy loop can actually find.

THE BUG THIS PINS (2026-09-02). Both adapter-kit legs expand a glob INCLUDE entry
(`use_cases/PFLOTRAN_miniLEO/*`) against the source tree, then the copy loop tests each
expanded entry with `[[ -e "$PRIVATE_REPO/$item" ]]`. The expander appended a trailing slash
to EVERY match:

    _EXPANDED+=("${rel%/}/")

which is correct for a directory and fatal for a file: `[[ -e "README.md/" ]]` is FALSE on
Linux, so the entry fell through to the else branch and printed

    [!] MISSING: use_cases/PFLOTRAN_miniLEO/README.md/

That line reads like a missing SOURCE file. It is not — it is a silent non-sync. The four LEO
cases shipped every subdirectory to A2MC-Saleska for weeks while never shipping their top-level
`README.md` / `research_plan.md`, and the only symptom was an inventory line nobody read as a
warning. Nothing downstream fails: the destination just quietly holds a stale copy forever.

So the assertion here is NOT "the source contains an `if [[ -d ]]`" — a grep for the fix would
pass against any rearrangement that reintroduces the defect. It EXECUTES the real expander block
lifted out of each leg, against a fixture holding one file and one directory, and asserts the
invariant the copy loop depends on: every emitted entry resolves with `-e`.

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Both adapter-kit legs are SEPARATE COPIES of the same script (the established per-leg pattern),
# so each carries its own copy of the expander and each has to be pinned. main's
# `sync_to_public.sh` is not listed: it has no glob expander at all and no globs in its INCLUDE
# list, and it is main's file besides.
LEGS = ["scripts/sync_adapterkit_to_public.sh", "scripts/sync_adapterkit_forSaleska.sh"]

_BLOCK_START = "_EXPANDED=()"
_BLOCK_END = 'INCLUDE_FILES=("${_EXPANDED[@]}")'


def _extract_expander(leg: Path) -> str:
    """Lift the expander block out of a leg so the TEST runs the SHIPPED code, not a copy."""
    lines = leg.read_text().splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == _BLOCK_START)
        end = next(i for i, ln in enumerate(lines) if ln.strip() == _BLOCK_END)
    except StopIteration:  # pragma: no cover - only when the leg is restructured
        pytest.fail(
            f"could not locate the glob-expander block in {leg.name} "
            f"(looked for {_BLOCK_START!r} .. {_BLOCK_END!r}). If the block moved, update this "
            "test — do not delete it; the defect it pins is invisible at runtime."
        )
    assert start < end, f"{leg.name}: expander markers out of order"
    return "\n".join(lines[start : end + 1])


def _run_expander(leg: Path, fixture: Path, tmp_path: Path) -> list[str]:
    harness = tmp_path / f"harness_{leg.stem}.sh"
    harness.write_text(
        "set -e\n"
        f'PRIVATE_REPO="{fixture}"\n'
        'INCLUDE_FILES=( "cases/*" )\n'
        f"{_extract_expander(leg)}\n"
        'printf "%s\\n" "${INCLUDE_FILES[@]}"\n'
    )
    out = subprocess.run(
        ["bash", str(harness)], capture_output=True, text=True, check=True
    ).stdout
    # The block itself prints a "[!] include glob matched nothing" line on a dead glob; keep it
    # out of the entry list but let a test below assert it did not fire.
    return [ln for ln in out.splitlines() if ln and not ln.lstrip().startswith("[!]")]


@pytest.fixture
def fixture_tree(tmp_path: Path) -> Path:
    """One file and one directory under a glob'd parent — the exact shape of a use case."""
    root = tmp_path / "src"
    (root / "cases" / "sub").mkdir(parents=True)
    (root / "cases" / "README.md").write_text("top-level file\n")
    (root / "cases" / "sub" / "inner.txt").write_text("nested\n")
    return root


def test_premise_a_file_with_a_trailing_slash_does_not_exist(fixture_tree: Path):
    """Anchors WHY this matters on this platform. If `-e` ever accepted `file/`, the original
    bug would have been harmless and these tests would be measuring nothing."""
    target = fixture_tree / "cases" / "README.md"
    assert target.is_file()
    probe = subprocess.run(
        ["bash", "-c", f'[[ -e "{target}/" ]]'], capture_output=True, text=True
    )
    assert probe.returncode != 0, (
        "`[[ -e <file>/ ]]` succeeded here, so the copy loop's existence test would accept a "
        "file entry carrying a trailing slash. This test's premise no longer holds — re-derive "
        "it before trusting the ones below."
    )


@pytest.mark.parametrize("leg_rel", LEGS)
def test_every_expanded_entry_resolves(leg_rel: str, fixture_tree: Path, tmp_path: Path):
    """THE INVARIANT. The copy loop skips any entry failing `[[ -e ]]`, and the skip is a
    printed line rather than an error — so an unresolvable entry is a silent non-sync."""
    leg = REPO / leg_rel
    if not leg.is_file():
        pytest.skip(f"{leg_rel} not present in this clone")
    entries = _run_expander(leg, fixture_tree, tmp_path)
    assert entries, f"{leg_rel}: expander produced no entries at all"
    unresolvable = [e for e in entries if not (fixture_tree / e).exists()]
    assert not unresolvable, (
        f"{leg_rel}: expanded entries the copy loop cannot resolve: {unresolvable}. "
        "These would be reported as '[!] MISSING' and silently never synced."
    )


@pytest.mark.parametrize("leg_rel", LEGS)
def test_file_matches_ship_and_directories_keep_their_slash(
    leg_rel: str, fixture_tree: Path, tmp_path: Path
):
    """A file must arrive WITHOUT a trailing slash (so `-e` finds it and the `cp`/filter branch
    handles it); a directory must KEEP one (rsync's transfer-root semantics depend on it)."""
    leg = REPO / leg_rel
    if not leg.is_file():
        pytest.skip(f"{leg_rel} not present in this clone")
    entries = _run_expander(leg, fixture_tree, tmp_path)
    assert "cases/README.md" in entries, (
        f"{leg_rel}: the glob's FILE match is missing or slash-suffixed. Got: {entries}. "
        "This is the 2026-09-02 defect — four LEO case READMEs never reached A2MC-Saleska."
    )
    assert "cases/sub/" in entries, (
        f"{leg_rel}: the glob's DIRECTORY match lost its trailing slash. Got: {entries}. "
        "rsync treats each included directory as its own transfer root; dropping the slash "
        "changes what --delete prunes."
    )
