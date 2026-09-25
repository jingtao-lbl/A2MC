"""The pre-commit hook's own WIRING, asserted -- not the checkers it calls.

Each checker has its own tests. Nothing tested the hook that invokes them, so a check could be
present, correct, and never reached: a dead gate, a renamed tool, a result computed and discarded,
or an early exit that skips everything after it all produce a clean commit, which is
indistinguishable from twenty-four checks passing.

The four assertions are the four layers an audit had to establish by hand, turned into code, plus
one that pins a property a downstream project repo depends on:

    1  no `exit 0` inside a check block -- it leaves the HOOK, not the check
    2  every referenced tool exists on disk
    3  every gate pattern matches at least one tracked path
    4  check numbers are unique
    5  every tool invocation is path-gated, or self-gates and is named here

Enumerate through git, never the filesystem: a gate is a claim about the BRANCH.

Run:  ~/a2mc_env/bin/python -m pytest tests/test_pre_commit_hook_wiring.py -q
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".githooks" / "pre-commit"

# Invocations that are deliberately NOT wrapped in a `git diff --cached` gate because the tool
# reads the staged index itself. Adding a name here is a claim that the tool self-gates; check it.
SELF_GATING = {"check_capability_change_logged.py"}


@pytest.fixture(scope="module")
def lines() -> list:
    return HOOK.read_text().splitlines()


@pytest.fixture(scope="module")
def tracked() -> list:
    """Every path git knows about, tracked or untracked-but-not-ignored."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO, stdout=subprocess.PIPE, universal_newlines=True).stdout
    return out.splitlines()


def _top_level_blocks(lines: list) -> list:
    """(start, end) of every column-0 `if ... fi`. Check blocks are all written at column 0."""
    blocks, stack = [], []
    for i, l in enumerate(lines):
        if l.startswith("if "):
            stack.append(i)
        elif l == "fi" and stack:
            blocks.append((stack.pop(), i))
    return blocks


def _headers(lines: list) -> list:
    """(number, line index) for each check HEADER.

    A header STARTS a comment block. `# (16) structure, ...` at the head of a continuation line is
    a cross-reference inside another check's prose, not a second check 16 -- distinguishing them is
    the whole difficulty, and a regex over line starts gets it wrong.
    """
    out = []
    for i, l in enumerate(lines):
        m = re.match(r"^# \((\d+)\)", l)
        if not m:
            continue
        prev = lines[i - 1].strip() if i else ""
        # A bare `#` is a separator INSIDE a header's own block, so it does not mean continuation;
        # a comment carrying text does. Getting this backwards drops checks (1) and (2), whose
        # headers sit under a `#` separator, and then reports their numbers as free.
        if prev.startswith("#") and prev != "#":
            continue
        out.append((int(m.group(1)), i))
    return out


# --------------------------------------------------------------------------- 1

def test_no_exit_0_inside_a_check_block(lines):
    """`exit 0` leaves the HOOK, so a check that uses it to skip itself skips everything after it.

    The safe form, used by most of the hook, is `if [[ -n "$PY" ]] && ! "$PY" ...`, which degrades
    to skipping only its own check.
    """
    last = max(i for i, l in enumerate(lines) if l.strip())
    bad = [i + 1 for i, l in enumerate(lines)
           if l.strip() == "exit 0" and i != last]
    assert bad == [], (
        f"`exit 0` at line(s) {bad} exits the HOOK, not the check. Every check after it is "
        f"silently skipped and the commit is reported clean. Use `if [[ -n \"$PY\" ]] && ! ...`.")


# --------------------------------------------------------------------------- 2

def test_every_referenced_tool_exists(lines):
    missing = sorted({t for t in re.findall(r"tools/[a-z_0-9]+\.py", "\n".join(lines))
                      if not (REPO / t).is_file()})
    assert missing == [], f"the hook invokes tool(s) that do not exist: {missing}"


# --------------------------------------------------------------------------- 3

def test_every_gate_matches_at_least_one_tracked_path(lines, tracked):
    """A gate matching nothing can never fire, and looks exactly like one that fires and passes.

    The precedent is real: `check_skill_claims.py` once tested for '/memory/dev_logs' with a
    leading slash, which git never emits, so that check skipped every dev log while reporting
    clean.
    """
    dead = []
    for pat in re.findall(r"grep -q?vE '([^']+)'", "\n".join(lines)):
        try:
            rx = re.compile(pat)
        except re.error:
            continue
        if not any(rx.search(p) for p in tracked):
            dead.append(pat)
    assert dead == [], f"gate pattern(s) match no tracked path, so they can never fire: {dead}"


# --------------------------------------------------------------------------- 4

def test_check_numbers_are_unique(lines):
    nums = [n for n, _ in _headers(lines)]
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    free = sorted(set(range(1, max(nums) + 1)) - set(nums)) if nums else []
    assert dupes == [], (
        f"check number(s) {dupes} are used twice, so a reference to one is ambiguous. "
        f"Free number(s) to move the LATER block to: {free or [max(nums) + 1]}")


# --------------------------------------------------------------------------- 5

def test_every_tool_invocation_is_path_gated(lines):
    """A downstream project repo chains its own hook to this one, and is safe only because every
    framework check is scoped to a framework path. An ungated check added later would start
    failing that project's commits with nobody intending it."""
    blocks = _top_level_blocks(lines)
    gated = [(a, b) for a, b in blocks
             if any("git diff --cached" in lines[k] for k in range(a, b + 1))]
    bad = []
    for i, l in enumerate(lines):
        m = re.search(r'"\$(?:PY|CAP_PY)"\s+"\$ROOT/(tools/[a-z_0-9]+\.py)"', l)
        if not m:
            continue
        tool = m.group(1).split("/")[-1]
        if tool in SELF_GATING:
            continue
        if not any(a <= i <= b for a, b in gated):
            bad.append((i + 1, tool))
    assert bad == [], (
        f"tool invocation(s) not inside a `git diff --cached` gate: {bad}. Either gate it on the "
        f"framework paths it governs, or add it to SELF_GATING with the reason it self-gates.")
