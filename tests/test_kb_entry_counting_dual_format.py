"""`check_workflow_state_offline._count_kb_entries` must support BOTH gained_knowledge formats.

THE BUG THESE TESTS PIN, measured 2026-09-09 at EcoSIM_Lusignan's round close. The checker read a
store as `payload.get(name, payload)`, which takes the ARRAY whenever the store's own key exists.
A seeded SITE store carries an empty array from its template PLUS its real entries as top-level
keys, which is the flat format `MemoryManager.add_discovery` writes and `_discovery_entries`
documents. So the checker reported "closed with empty site-KB store(s): discoveries" on a file
that `MemoryManager.stats()` read as holding seven, immediately after those seven were curated.

A checker and the library it checks disagreeing about the same file is a bug in one of them
(root `CLAUDE.md`, "When documents disagree"), and it was in the checker: `MemoryManager` supports
both formats by design and says so in `_discovery_entries`' own docstring.

**Every test below is written as a way the counter must FAIL if the fix is removed**
([[feedback_a_check_that_cannot_fail]]). The two that matter most are `test_seeded_site_store_*`,
which is the measured bug, and `test_genuinely_empty_store_still_counts_zero`, which is the
negative control: the fix must not silence a TRUE empty-store warning. Both were confirmed
against the live tree before this file was written -- the false warning on EcoSIM_Lusignan
cleared and the true one on PFLOTRAN_miniLEO (empty experiments, parameters and failed_approaches)
survived.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _counter():
    sp = importlib.util.spec_from_file_location(
        "chk_wso", ROOT / "tools" / "check_workflow_state_offline.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m._count_kb_entries


count = _counter()


# ---- the measured bug -------------------------------------------------------------------

def test_seeded_site_store_counts_its_flat_entries_not_its_empty_array():
    """THE BUG. An empty template array beside real flat entries must count the entries."""
    payload = {"_comment": "seeded template", "discoveries": []}
    payload.update({f"finding_{i}": {"description": "x"} for i in range(7)})
    assert count(payload, "discoveries") == 7


def test_seeded_site_store_with_only_the_empty_array_is_still_zero():
    """The negative control for the test above: the fix must not invent entries."""
    assert count({"_comment": "seeded template", "discoveries": []}, "discoveries") == 0


# ---- the format each store family actually uses -----------------------------------------

def test_array_format_model_level_store():
    """The model-level store keys its entries by `id` inside the named array."""
    payload = {"_comment": "x", "discoveries": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
    assert count(payload, "discoveries") == 3


def test_flat_format_site_store():
    """The site store writes `name -> entry` at the top level, with no array at all."""
    payload = {"_comment": "x", "_scope": "y", "alpha": {"k": 1}, "beta": {"k": 2}}
    assert count(payload, "discoveries") == 2


def test_both_formats_populated_are_unioned_not_shadowed():
    payload = {"discoveries": [{"id": "a"}, {"id": "b"}], "gamma": {"k": 1}}
    assert count(payload, "discoveries") == 3


# ---- what must NOT be counted ------------------------------------------------------------

def test_genuinely_empty_store_still_counts_zero():
    """THE LOAD-BEARING NEGATIVE CONTROL. A true empty-store warning must survive the fix.

    PFLOTRAN_miniLEO's `experiments`, `parameters` and `failed_approaches` are exactly this
    shape, and their warning must keep firing.
    """
    assert count({"_comment": "x", "_schema_version": "1.0", "experiments": []}, "experiments") == 0
    assert count({"_comment": "x", "parameters": {}}, "parameters") == 0


def test_metadata_strings_are_not_entries():
    payload = {"_comment": "a string", "_scope": "another", "_source": "a third",
               "discoveries": []}
    assert count(payload, "discoveries") == 0


def test_a_top_level_non_dict_is_not_an_entry():
    """Only dict-valued top-level keys are entries; a stray scalar must not inflate the count."""
    payload = {"discoveries": [], "some_flag": True, "some_note": "text", "real": {"k": 1}}
    assert count(payload, "discoveries") == 1


def test_dict_shaped_named_key_counts_its_members():
    """`parameters.json` uses a dict under its own key rather than a list."""
    payload = {"_comment": "x", "parameters": {"CNWL": {}, "SPOSC": {}, "_meta": "s"}}
    assert count(payload, "parameters") == 2


@pytest.mark.parametrize("payload", [[], [1, 2, 3], "not a mapping", None])
def test_non_mapping_payloads_do_not_raise(payload):
    """A malformed store must return a count rather than crash the whole checker."""
    n = count(payload, "discoveries")
    assert isinstance(n, int) and n >= 0
