"""A skill that belongs to one model must SAY so, because a subset is derived from the declaration.

visibility: public

WHY. `create-project-agent` delivers only the models a project uses. Model-scoped PATHS derive
themselves -- `docs/<model>-knowledge-base/`, `models/<model>/`, `memory/<model>/` are each named
for their model -- but SKILLS carry the fact only in `modes.scope`. When that field does not carry
it, the derivation is silently wrong in the worst direction: a model's skill ships to a project
that has no such model, and the project's own model loses a skill it needed.

The CONTROLS matter more than the rule here. A skill with no model in its scope is treated as
model-AGNOSTIC and travels everywhere, which is the safe default and the common case (47 of 54).
So the test that can actually fail is the one asserting a model-scoped skill is dropped for a
project that did not ask for its model -- without it, "everything travels" passes silently.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "skill_models.py"
SKILLS = REPO / ".claude" / "skills"


@pytest.fixture(scope="module")
def sm():
    if not TOOL.is_file():
        pytest.skip("tools/skill_models.py is not present in this clone")
    spec = importlib.util.spec_from_file_location("_sm", TOOL)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_sm"] = m
    spec.loader.exec_module(m)
    return m


# ---- the rule --------------------------------------------------------------------------------
def test_a_skill_that_implies_a_model_declares_it(sm):
    """Implied by the directory name, or by `requires_fates: true`. Either way it must be in scope
    so a derivation can see it."""
    bad = []
    for f in sorted(SKILLS.glob("*/SKILL.md")):
        name = f.parent.name
        text = f.read_text(errors="replace")
        implied = {k for k in sm.MODELS if k in name.lower()}
        if re.search(r"^\s*requires_fates:\s*true", text, re.M):
            implied.add("fates")
        if implied and not implied <= sm.skill_models(f):
            bad.append((name, sorted(implied), sorted(sm.skill_models(f))))
    assert bad == [], (
        "skill(s) imply a model their `modes.scope` does not declare: %r. A per-model subset is "
        "DERIVED from that field, so an undeclared model means the skill ships to projects that do "
        "not have it and is kept out of nothing." % bad)


# ---- controls --------------------------------------------------------------------------------
def test_CONTROL_a_model_scoped_skill_is_DROPPED_for_another_model(sm):
    """The test that can fail. Without it, a resolver that returns everything passes."""
    dropped = sm.drop_for({"ecosim"})
    assert "pflotran-run-workflow" in dropped
    assert "ats-run-workflow" in dropped
    assert "ecosim-run-workflow" not in dropped, "a skill for the requested model was dropped"


def test_CONTROL_an_agnostic_skill_is_kept_for_every_model(sm):
    """The safe default: carrying a skill a project did not need is cheap, losing one is not."""
    for model in sm.MODELS:
        kept = sm.keep_for({model})
        assert "plotting" in kept and "log" in kept, (
            "a model-agnostic skill was dropped for %s" % model)


def test_CONTROL_requires_fates_alone_is_honoured(sm, tmp_path):
    """An older skill may declare FATES only through `requires_fates`. Treating it as agnostic
    would ship it to every project."""
    f = tmp_path / "SKILL.md"
    f.write_text("---\nname: x\nmodes:\n  requires_fates: true\n  scope: [analysis]\n---\n")
    assert sm.skill_models(f) == {"fates"}


def test_CONTROL_an_unknown_model_is_refused_not_silently_empty(sm):
    """`--models ecosm` (a typo) must not quietly select nothing."""
    with pytest.raises(SystemExit):
        sm._parse_models("ecosm")


def test_keep_and_drop_partition_the_catalogue(sm):
    """Every skill goes to exactly one side; nothing is lost between them."""
    wanted = {"ecosim"}
    keep, drop = set(sm.keep_for(wanted)), set(sm.drop_for(wanted))
    allnames = set(sm.all_skills())
    assert keep | drop == allnames
    assert keep & drop == set()
