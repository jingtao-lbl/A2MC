"""The pre-commit hook's own WIRING, asserted -- not the checkers it calls.

Each checker has its own tests. Nothing tested the hook that invokes them, so a check could be
present, correct, and never reached: a dead gate, a renamed tool, a result computed and discarded,
or an early exit that skips everything after it all produce a clean commit, which is
indistinguishable from twenty-four checks passing.

The four assertions are the four layers an audit had to establish by hand, turned into code, plus
one that pins a property a downstream project repo depends on:

    1  no `exit 0` inside a check block -- it leaves the HOOK, not the check
    2  every referenced tool exists on disk (in the development repo; a downstream copy may lack a
       private tool), every literal call goes through run_tool, the hook's downstream rule matches
       tools/downstream.py, and run_tool skips downstream and fails here
    3  every gate pattern matches at least one tracked path
    4  check numbers are unique
    5  every tool invocation is path-gated, or self-gates and is named here

Enumerate through git, never the filesystem: a gate is a claim about the BRANCH.

Run:  ~/a2mc_env/bin/python -m pytest tests/test_pre_commit_hook_wiring.py -q
"""

from __future__ import annotations

import re
import subprocess
import sys
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
    """In the DEVELOPMENT repo every tool the hook names must exist: run_tool fails on a missing
    one there, so this catches it before a commit does. In a downstream copy a `visibility: private`
    tool is legitimately absent and run_tool skips its check, so absence is not an error there."""
    sys.path.insert(0, str(REPO / "tools"))
    import downstream
    if downstream.is_downstream(REPO):
        pytest.skip("downstream copy: private tools are absent by design and run_tool skips them")
    missing = sorted({t for t in re.findall(r"tools/[a-z_0-9]+\.py", "\n".join(lines))
                      if not (REPO / t).is_file()})
    assert missing == [], f"the hook invokes tool(s) that do not exist: {missing}"


def test_every_literal_tool_call_goes_through_run_tool(lines):
    """A call that bypasses run_tool fails in a downstream copy that does not carry the tool, which
    is exactly the failure run_tool exists to prevent. A call naming its tool through a variable
    must carry its own `[[ -f ]]` test instead (the graph-freshness loop does)."""
    bare = [(i + 1, l.strip()) for i, l in enumerate(lines)
            if re.search(r'(?<!run_tool )"\$(?:PY|CAP_PY)"\s+"\$ROOT/tools/[a-z_0-9]+\.py"', l)]
    assert bare == [], f"tool call(s) not routed through run_tool: {bare}"


def _hook_functions(lines: list, *names: str) -> str:
    """The text of the named shell functions, cut from the hook itself rather than copied here."""
    text = "\n".join(lines)
    out = []
    for name in names:
        m = re.search(r"^%s\(\) \{\n.*?^\}\n" % re.escape(name), text + "\n", re.S | re.M)
        assert m, f"the hook defines no function {name}()"
        out.append(m.group(0))
    return "\n".join(out)


def test_the_hooks_downstream_rule_matches_tools_downstream(lines, tmp_path):
    """The hook restates tools/downstream.py's predicate in shell. Run both on the same trees."""
    sys.path.insert(0, str(REPO / "tools"))
    import downstream
    fn = _hook_functions(lines, "a2mc_is_downstream")
    cases = {"marked": [".a2mc-downstream"], "marked_with_dev_logs": [".a2mc-downstream", "memory/dev_logs_x/"],
             "dev_logs_only": ["memory/dev_logs/"], "neither": []}
    for name, paths in cases.items():
        root = tmp_path / name
        root.mkdir()
        for rel in paths:
            q = root / rel
            q.mkdir(parents=True) if rel.endswith("/") else q.write_text("x\n")
        shell = subprocess.run(["bash", "-c", fn + '\na2mc_is_downstream "$1"', "_", str(root)]).returncode == 0
        assert shell == downstream.is_downstream(root), f"{name}: hook says {shell}, downstream.py disagrees"


def test_run_tool_skips_downstream_and_fails_in_the_development_repo(lines, tmp_path):
    fn = _hook_functions(lines, "a2mc_is_downstream", "run_tool")
    def run(root):
        return subprocess.run(["bash", "-c", fn + '\nROOT="$1"; run_tool python3 "$ROOT/tools/gone.py"', "_", str(root)],
                              stderr=subprocess.PIPE, universal_newlines=True)
    copy = tmp_path / "copy"; copy.mkdir(); (copy / ".a2mc-downstream").write_text("x\n")
    dev = tmp_path / "dev"; (dev / "memory" / "dev_logs").mkdir(parents=True)
    r = run(copy)
    assert r.returncode == 0 and "is not in this copy" in r.stderr, r.stderr
    r = run(dev)
    assert r.returncode == 1 and "MISSING in the development repo" in r.stderr, r.stderr


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
