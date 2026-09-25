"""A new test or tool must declare whether it ships, and the legs must act on the declaration.

visibility: public

WHY. `tests/` and `tools/` are whole INCLUDE paths on both sync legs, so a new file ships the
moment it is committed and nothing asks whether it should. A skill answers this in its frontmatter
and the legs derive the exclusion from it; a script had no equivalent. `tools/check_script_visibility.py`
asks for the same one-line declaration, non-retroactively.

The CONTROLS are what make this a check rather than a formality: the rule must actually FAIL on an
undeclared new file, it must EXEMPT a file that predates it, the declaration must be in the header
rather than anywhere in the file, and both legs must really derive an exclusion from it -- an
exclude that matches nothing looks exactly like one that works.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "check_script_visibility.py"


@pytest.fixture(scope="module")
def csv_mod():
    if not TOOL.is_file():
        pytest.skip("check_script_visibility.py is not present in this clone")
    spec = importlib.util.spec_from_file_location("_csv_vis", TOOL)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_csv_vis"] = m
    spec.loader.exec_module(m)
    return m


def _write(tmp_path: Path, rel: str, text: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


# ---- the declaration ----------------------------------------------------------------------------
@pytest.mark.parametrize("body,expected", [
    ('"""Doc.\n\nvisibility: public\n"""\n', "public"),
    ('"""Doc.\n\nvisibility: private\n"""\n', "private"),
    ("#!/usr/bin/env python3\n# visibility: private\n", "private"),
    ("#!/bin/bash\n#  visibility:  public \n", "public"),
    ('"""Doc with no declaration."""\n', ""),
    ('"""Doc.\n\nvisibility: maybe\n"""\n', ""),          # only the two values count
])
def test_declaration_forms(csv_mod, tmp_path, body, expected):
    p = _write(tmp_path, "t.py", body)
    assert csv_mod.declared(p) == expected


def test_CONTROL_a_declaration_below_the_header_does_not_count(csv_mod, tmp_path):
    """A `visibility:` deep in a file is prose about something else, not this file's declaration."""
    body = '"""Doc."""\n' + "\n" * (csv_mod.HEADER_LINES + 5) + "# visibility: private\n"
    p = _write(tmp_path, "t.py", body)
    assert csv_mod.declared(p) == ""


# ---- scope --------------------------------------------------------------------------------------
@pytest.mark.parametrize("rel,expected", [
    ("tools/check_x.py", True),
    ("tests/test_x.py", True),
    ("scripts/wrap_for_project_agent.sh", True),   # scripts/ ships wholesale too
    ("tools/check_partition_health.sh", True),
    ("tools/__init__.py", False),
    ("tests/conftest.py", False),
    ("models/ecosim/spec.py", False),          # ships, but is framework code, not a check
    ("tools/doc_claims.yaml", False),
])
def test_scope(csv_mod, rel, expected):
    assert csv_mod.in_scope(rel) is expected


# ---- the rule, and that it can fail --------------------------------------------------------------
def test_an_undeclared_new_file_is_a_problem(csv_mod, tmp_path, monkeypatch):
    monkeypatch.setattr(csv_mod, "ROOT", tmp_path)
    monkeypatch.setattr(csv_mod, "added_date", lambda p: "")      # never committed = being written now
    _write(tmp_path, "tools/check_probe.py", '"""No declaration."""\n')
    problems, checked, exempt = csv_mod.check(["tools/check_probe.py"])
    assert problems == ["tools/check_probe.py"]
    assert (checked, exempt) == (1, 0)


def test_a_declared_new_file_is_clean(csv_mod, tmp_path, monkeypatch):
    monkeypatch.setattr(csv_mod, "ROOT", tmp_path)
    monkeypatch.setattr(csv_mod, "added_date", lambda p: "")
    _write(tmp_path, "tools/check_probe.py", '"""Doc.\n\nvisibility: public\n"""\n')
    problems, checked, exempt = csv_mod.check(["tools/check_probe.py"])
    assert problems == [] and (checked, exempt) == (1, 0)


def test_CONTROL_a_file_predating_the_rule_is_exempt(csv_mod, tmp_path, monkeypatch):
    """Non-retroactive, per the instruction that this is for FUTURE scripts."""
    monkeypatch.setattr(csv_mod, "ROOT", tmp_path)
    monkeypatch.setattr(csv_mod, "added_date", lambda p: "2026-01-01")
    _write(tmp_path, "tools/check_old.py", '"""No declaration."""\n')
    problems, checked, exempt = csv_mod.check(["tools/check_old.py"])
    assert problems == [], "a pre-existing script was retroactively flagged"
    assert (checked, exempt) == (0, 1)


def test_CONTROL_a_file_added_on_the_effective_date_IS_checked(csv_mod, tmp_path, monkeypatch):
    """The boundary is inclusive, so the rule starts biting rather than starting a day late."""
    monkeypatch.setattr(csv_mod, "ROOT", tmp_path)
    monkeypatch.setattr(csv_mod, "added_date", lambda p: csv_mod.EFFECTIVE)
    _write(tmp_path, "tools/check_edge.py", '"""No declaration."""\n')
    problems, _, _ = csv_mod.check(["tools/check_edge.py"])
    assert problems == ["tools/check_edge.py"]


# ---- the legs must act on it ---------------------------------------------------------------------
def test_CONTROL_every_leg_derives_an_exclusion_from_the_declaration():
    """A declaration nothing reads is a comment. Every leg must build PRIVATE_SCRIPTS and append
    it to EXCLUDE_PATTERNS, by BASENAME -- slash-free, because each included directory is its own
    rsync transfer root and a slash-bearing pattern would match nothing.

    The legs are DISCOVERED, never named. A leg is named for its destination, so a hand-list here
    would publish a private one: this file ships, and its own filename carries no `sync`, so the
    exclusion that withholds the legs' tests does not cover it. Discovery also picks up a leg added
    later, which a hand-list would silently skip."""
    legs = sorted((REPO / "scripts").glob("sync_*.sh"))
    if not legs:
        pytest.skip("no sync leg in this clone (a downstream copy does not carry them)")
    for leg in legs:
        text = leg.read_text()
        assert "PRIVATE_SCRIPTS" in text, f"{leg.name} does not derive private scripts"
        assert 'visibility:[[:space:]]*private' in text, f"{leg.name} does not read the declaration"
        assert 'EXCLUDE_PATTERNS+=("$_ps")' in text, f"{leg.name} derives but never excludes"
        assert 'basename "$_f"' in text, (
            f"{leg.name} must exclude by BASENAME; a slash-bearing pattern is matched inside the "
            f"transfer root and would hit nothing")


def test_CONTROL_the_checker_declares_its_own_visibility(csv_mod):
    """It is wired into the shipped pre-commit, so it cannot be private without the hook first
    learning to skip a missing tool. It must say which it is."""
    assert csv_mod.declared(TOOL) == "public"
