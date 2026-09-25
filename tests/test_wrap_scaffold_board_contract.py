"""The generated project board must speak the vocabulary its own skill specifies.

visibility: public

WHY. `scripts/_wrap_scaffold.sh` generates a project's `state.py`, `todo.py` and session-start
hook. `create-project-agent` Step 6 specifies the board contract those must implement. Nothing
compared the two, so the scaffold shipped a four-value enum using `open` where the contract says
`pending`, with no `blocked` at all -- while the contract's task record carries `blockedBy[]` to
pair with it. A project board could not express a blocked task, and `next` could only answer "what
is OPEN" rather than "what is READY", which pushes the real dependency into prose inside a note
where nothing can read it.

THE BINDING IS THE POINT. These tests derive the expected vocabulary FROM THE SKILL rather than
restating it, so a change to either side alone fails here instead of drifting silently. A test that
pinned the five names literally would have to be edited in lockstep with both, which is the same
two-copies problem one level up.

Account: `memory/dev_logs_adapterkit/20260925f_The_Scaffold_Spoke_Its_Own_Board_Vocabulary.md`.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCAFFOLD = REPO / "scripts" / "_wrap_scaffold.sh"
SKILL = REPO / ".claude" / "skills" / "create-project-agent" / "SKILL.md"


@pytest.fixture(scope="module")
def scaffold() -> str:
    if not SCAFFOLD.is_file():
        pytest.skip("the scaffold is not present in this clone")
    return SCAFFOLD.read_text()


@pytest.fixture(scope="module")
def contract_statuses() -> set:
    """The enum AS THE SKILL STATES IT -- derived, never restated here."""
    if not SKILL.is_file():
        pytest.skip("create-project-agent is not present in this clone")
    m = re.search(r"status enum is exactly .?\{([^}]*)\}", SKILL.read_text())
    assert m, "Step 6 no longer states the enum in the form this test reads -- reconcile both"
    names = {x.strip().strip("`") for x in m.group(1).split(",")}
    assert len(names) >= 4, "parsed only %r from the skill; the parse went blind" % names
    return names


# ---- the binding --------------------------------------------------------------------------------
def test_the_scaffold_declares_exactly_the_contract_statuses(scaffold, contract_statuses):
    m = re.search(r"^STATUSES = \(([^)]*)\)", scaffold, re.M)
    assert m, "the generated state.py no longer declares STATUSES"
    got = {x.strip().strip('"').strip("'") for x in m.group(1).split(",") if x.strip()}
    assert got == contract_statuses, (
        "the scaffold and its own skill disagree about the task-status enum.\n"
        "  skill says:    %s\n  scaffold has:  %s\n"
        "Fix BOTH in one pass; a board that invents its own vocabulary cannot move between projects."
        % (sorted(contract_statuses), sorted(got)))


def _seed_task_block(scaffold: str) -> str:
    """The seed board's tasks array ONLY.

    Scoped deliberately: the board carries a top-level `note` key that the contract's ten keys
    include, so a whole-file grep for `"note":` flags a correct line. The divergence was in the
    TASK record, and that is what this reads."""
    i = scaffold.index('"tasks": [')
    return scaffold[i:scaffold.index("]", i)]


def test_CONTROL_the_retired_vocabulary_is_gone(scaffold):
    """`open` as a status and `title`/`note` as TASK fields were the divergence, and each must
    stay gone. Anchored to the seed task, not the file."""
    block = _seed_task_block(scaffold)
    assert '"status": "open"' not in block, "the seed task is `open`; the contract says `pending`"
    assert '"title":' not in block, "the seed task uses `title`; the contract says `subject`"
    assert re.search(r'^\s*"note":', block, re.M) is None, (
        "the seed task uses `note`; the contract says `detail` for the body and `notes` for a list")


def test_CONTROL_the_board_level_note_key_is_UNAFFECTED(scaffold):
    """The opposite error: scoping the check above by deleting a legitimate key. `note` is one of
    the contract's ten top-level keys and must survive."""
    assert re.search(r'^\s*"note": "The board\.', scaffold, re.M), (
        "the board-level `note` key is gone; it is one of the contract's ten and is not a task field")


# ---- the seed board the scaffold writes ----------------------------------------------------------
@pytest.mark.parametrize("field", ["subject", "detail", "status", "owner", "blockedBy", "notes"])
def test_the_seed_task_carries_the_contract_record(scaffold, field):
    assert '"%s":' % field in scaffold, (
        "the seed task has no %r, so the first board a project ever sees is already off-contract"
        % field)


# ---- what blockedBy is FOR -----------------------------------------------------------------------
def test_next_is_dependency_aware_not_merely_open(scaffold):
    """Without this, `blockedBy` is a field nothing reads, and the dependency lives in prose."""
    assert "def ready(" in scaffold, "the generated state.py has no readiness predicate"
    block = scaffold.split("def ready(")[1][:600]
    assert "blockedBy" in block and "completed" in block, (
        "readiness does not consult blockedBy, so `next` answers 'what is open' rather than "
        "'what is ready'")


def test_check_validates_the_dependency_graph(scaffold):
    """A board that can deadlock itself should say so rather than hang `next`."""
    for needle, why in (
            ("is blockedBy", "a blocker that is not a task goes unreported"),
            ("dependency cycle", "a cycle is not detected"),
            ("still blockedBy", "a completed task blocked by an unfinished one goes unreported")):
        assert needle in scaffold, "state.py check: %s" % why


def test_the_generated_views_render_blocked(scaffold):
    """A status the board can hold but no view can show is a status people stop using."""
    assert '("blocked", "Blocked")' in scaffold, "todo.py has no Blocked section"
    assert "waits on" in scaffold, "todo.py does not show what a task waits on"
