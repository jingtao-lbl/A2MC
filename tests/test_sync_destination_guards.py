"""The Saleska leg must REFUSE a dirty destination, and must not be talked out of it by accident.

WHY THE GUARD EXISTS. `A2MC-Saleska` is a shared PRIVATE repo with external contributors
(docs/40 §2), while the leg feeding it is a one-way `rsync --delete` applied per included path.
Work a teammate added inside an included directory and has not committed is destroyed with no
record anywhere — committed work is recoverable from the destination's own git history,
uncommitted work is not. The guard turns the single unrecoverable loss into a stop.

WHY IT IS TESTED HERE RATHER THAN BY RUNNING THE LEG. Exercising the `--allow-dirty` branch
end-to-end would perform a real sync into a real destination, so the branch that must NOT stop
would be the expensive one to check and would go unchecked. This lifts the guard block out of the
shipped script and drives all three branches against a throwaway git repo instead.

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LEG = REPO / "scripts" / "sync_adapterkit_forSaleska.sh"

_GUARD_START = '_dest_dirty="$(git -C "$SALESKA_REPO" status --porcelain 2>/dev/null || true)"'
_REPORT_START = "if [[ ${#DELETIONS[@]} -eq 0 ]]; then"


def _extract_guard() -> str:
    """Lift the guard out of the shipped leg, so the test cannot pass against a script that
    no longer contains it."""
    if not LEG.is_file():
        pytest.skip("the Saleska leg is not present in this clone")
    lines = LEG.read_text().splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == _GUARD_START)
    except StopIteration:  # pragma: no cover - only when the guard is removed or rewritten
        pytest.fail(
            "the dirty-destination guard is gone from scripts/sync_adapterkit_forSaleska.sh "
            f"(looked for {_GUARD_START!r}). It is the only thing standing between an external "
            "contributor's uncommitted work and `rsync --delete`. Do not delete this test to "
            "make it pass."
        )
    # The guard is one `if [[ -n "$_dest_dirty" ]]; then ... fi` block: take to its closing `fi`
    # at column 0, which is unambiguous because every nested `fi` inside it is indented.
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "fi")
    return "\n".join(lines[start : end + 1])


@pytest.fixture
def dest(tmp_path: Path) -> Path:
    d = tmp_path / "A2MC-Saleska"
    d.mkdir()
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    (d / "tracked.md").write_text("committed\n")
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed"],
        check=True,
    )
    return d


def _run(dest: Path, tmp_path: Path, *, dry_run: bool, allow_dirty: bool):
    harness = tmp_path / f"guard_{int(dry_run)}{int(allow_dirty)}.sh"
    harness.write_text(
        "set -e\n"
        f'SALESKA_REPO="{dest}"\n'
        f'DRY_RUN={str(dry_run).lower()}\n'
        f'ALLOW_DIRTY={str(allow_dirty).lower()}\n'
        f"{_extract_guard()}\n"
        'echo "REACHED_THE_SYNC"\n'
    )
    return subprocess.run(["bash", str(harness)], capture_output=True, text=True)


def test_clean_destination_passes_silently(dest: Path, tmp_path: Path):
    r = _run(dest, tmp_path, dry_run=False, allow_dirty=False)
    assert r.returncode == 0 and "REACHED_THE_SYNC" in r.stdout
    assert "DIRTY" not in r.stderr, "a clean tree must not warn — a guard that cries wolf gets -f'd"


@pytest.mark.parametrize(
    "dirty",
    [
        pytest.param("untracked", id="untracked-teammate-file"),
        pytest.param("modified", id="modified-tracked-file"),
    ],
)
def test_dirty_destination_is_refused(dest: Path, tmp_path: Path, dirty: str):
    """THE POINT OF THE GUARD. Both shapes matter: an untracked file is the teammate's new work,
    a modified tracked file is their edit to something the sync also ships."""
    if dirty == "untracked":
        (dest / "teammate_note.md").write_text("uncommitted\n")
    else:
        (dest / "tracked.md").write_text("edited by a teammate\n")
    r = _run(dest, tmp_path, dry_run=False, allow_dirty=False)
    assert r.returncode == 1, f"a dirty destination was NOT refused ({dirty})"
    assert "REACHED_THE_SYNC" not in r.stdout, "the guard let execution continue past it"
    assert "--allow-dirty" in r.stderr, "the refusal must say how to proceed deliberately"


def test_dry_run_warns_but_does_not_refuse(dest: Path, tmp_path: Path):
    """A preview writes nothing, and the preview is exactly when you want to learn the
    destination is dirty — before committing to the real run."""
    (dest / "teammate_note.md").write_text("uncommitted\n")
    r = _run(dest, tmp_path, dry_run=True, allow_dirty=False)
    assert r.returncode == 0 and "REACHED_THE_SYNC" in r.stdout
    assert "DIRTY" in r.stderr and "would REFUSE" in r.stderr


def test_allow_dirty_proceeds_with_a_warning(dest: Path, tmp_path: Path):
    """The deliberate override still has to SAY it overrode something — a silent opt-out is how
    the flag ends up pasted into a runbook and never reconsidered."""
    (dest / "teammate_note.md").write_text("uncommitted\n")
    r = _run(dest, tmp_path, dry_run=False, allow_dirty=True)
    assert r.returncode == 0 and "REACHED_THE_SYNC" in r.stdout
    assert "DIRTY" in r.stderr and "--allow-dirty" in r.stderr


def test_unknown_argument_is_rejected():
    """The old parser tested "$1" only, so `--allow-dirty --dry-run` would have run a REAL sync.
    Unknown arguments must fail loudly rather than being ignored."""
    if not LEG.is_file():
        pytest.skip("the Saleska leg is not present in this clone")
    r = subprocess.run([str(LEG), "--no-such-flag"], capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 1
    assert "unknown argument" in r.stderr
    assert "[--dry-run] [--allow-dirty]" in r.stderr


# ---------------------------------------------------------------------------
# The deletion report
#
# `rsync --delete` removing a path is the one action in this sync that destroys someone else's
# work rather than updating ours, and it is the hardest to see: in the destination's `git status`
# a few D lines sit among hundreds of M lines, under a runbook step that says `git add -A`. The
# report is the review surface for COMMITTED work in the destination, the way the dirty-tree
# guard above is the guard for uncommitted work.
# ---------------------------------------------------------------------------


def _extract_report() -> str:
    if not LEG.is_file():
        pytest.skip("the Saleska leg is not present in this clone")
    lines = LEG.read_text().splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == _REPORT_START)
    except StopIteration:  # pragma: no cover - only when the report is removed or rewritten
        pytest.fail(
            "the deletion report is gone from scripts/sync_adapterkit_forSaleska.sh "
            f"(looked for {_REPORT_START!r}). Without it a --delete of a teammate's committed "
            "work is reviewed only as a D line among hundreds of M lines."
        )
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "fi")
    return "\n".join(lines[start : end + 1])


def _run_report(tmp_path: Path, deletions: list[str], *, dry_run: bool):
    harness = tmp_path / f"report_{int(dry_run)}_{len(deletions)}.sh"
    arr = " ".join(f'"{d}"' for d in deletions)
    harness.write_text(
        "set -e\n"
        f'DRY_RUN={str(dry_run).lower()}\n'
        f"DELETIONS=({arr})\n"
        f"{_extract_report()}\n"
    )
    return subprocess.run(["bash", str(harness)], capture_output=True, text=True)


def test_no_deletions_says_so_explicitly(tmp_path: Path):
    """Silence would be indistinguishable from a report that failed to run."""
    r = _run_report(tmp_path, [], dry_run=False)
    assert r.returncode == 0
    assert "nothing removed from the destination" in r.stdout


def test_deletions_are_listed_with_a_count(tmp_path: Path):
    paths = ["tools/teammate_helper.py", "use_cases/PFLOTRAN_LEO/reports/team_note.md"]
    r = _run_report(tmp_path, paths, dry_run=False)
    assert r.returncode == 0
    assert "2 path(s) REMOVED" in r.stdout
    for pth in paths:
        assert pth in r.stdout, f"a removed path went unreported: {pth}"


def test_dry_run_reports_in_the_conditional(tmp_path: Path):
    """A preview must not claim it removed anything — the useful moment to see this list is
    BEFORE the sync, and the wording is what tells the reader which one they are looking at."""
    r = _run_report(tmp_path, ["tools/teammate_helper.py"], dry_run=True)
    assert r.returncode == 0
    assert "WOULD BE REMOVED" in r.stdout
    assert "path(s) REMOVED" not in r.stdout
