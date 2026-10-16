"""The per-model knowledge-base tools table in the memory bucket must stay true.

visibility: public

`reference_per_model_kb_build_tools` is the one place the whole matrix of knowledge-base tools sits, per
step and per model, and the edit-time reminder sends the agent there before every KB edit. A table
copied out of the code drifts silently (`feedback_bind_derived_facts_to_their_source`); the KB
skills' own profile lists went stale exactly that way, naming one EcoSIM profile after a second was
registered. So two facts in it are bound to their source here:

1. every tool it names exists, on this branch or, for the rows marked "(ATS branch only)", on the
   ATS feature branch when that ref is present;
2. the "registered profiles" row lists exactly the profiles in `rag/milestones.json`.

`.claude_memory/` never ships, so a released tree without the bucket skips this file.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MEM = REPO / ".claude_memory" / "reference_per_model_kb_build_tools.md"
ATS_REF = "origin/A2MC-adapter-kit-ATS"

pytestmark = pytest.mark.skipif(not MEM.is_file(), reason="the memory bucket does not ship")


def _table_rows():
    return [ln for ln in MEM.read_text().splitlines() if ln.startswith("| ") and not ln.startswith("|---")]


def _git(*args):
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    return r.returncode, r.stdout


def test_the_profiles_row_matches_the_registry():
    row = next((r for r in _table_rows() if r.startswith("| registered profiles")), None)
    assert row, "no 'registered profiles' row -- the table's shape changed"
    listed = set(re.findall(r"`([^`]+)`", row))
    registered = set(json.loads((REPO / "rag" / "milestones.json").read_text())["milestones"])
    assert listed == registered, (
        "the memory's profiles row and rag/milestones.json disagree: only in the memory %s, only in "
        "the registry %s. Update the row in the same commit that registers or retires a profile."
        % (sorted(listed - registered), sorted(registered - listed)))


def _tool_tokens():
    """(tool, row) for every backticked token whose first word is a .py file."""
    out = []
    for row in _table_rows():
        for tok in re.findall(r"`([^`]+)`", row):
            first = tok.split()[0]
            if first.endswith(".py") and "<" not in first:
                out.append((first, row))
    return out


def test_every_tool_named_exists():
    tokens = _tool_tokens()
    assert len(tokens) > 20, "too few tools parsed (%d) -- the parser no longer reads the table" % len(tokens)
    rc, _ = _git("rev-parse", "--verify", "--quiet", ATS_REF)
    ats_ref = rc == 0
    missing = []
    for tool, row in tokens:
        cands = [tool] if "/" in tool else ["tools/" + tool, "scripts/" + tool]
        if any((REPO / c).is_file() for c in cands):
            continue
        if "(ATS branch only)" in row:
            if not ats_ref:
                continue                      # the ref is not fetched in this clone; nothing to check
            if any(_git("cat-file", "-e", "%s:%s" % (ATS_REF, c))[0] == 0 for c in cands):
                continue
        missing.append(tool)
    assert not missing, ("the memory names tools that do not exist: %s. Retired or renamed? Update "
                         "the row with the skill's own slice, in one commit." % sorted(set(missing)))


def test_CONTROL_a_removed_tool_would_be_caught():
    """The check must be able to fail: a name that exists nowhere is not resolved by the lookup."""
    assert not any((REPO / c).is_file() for c in ("tools/build_nonexistent_rag.py",
                                                  "scripts/build_nonexistent_rag.py"))
    names = {t for t, _ in _tool_tokens()}
    assert "build_ecosim_rag.py" in names and "check_rag_queries.py" in names, names
