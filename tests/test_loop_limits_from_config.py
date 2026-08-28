"""The offline loop limits must come from the MACHINE CONFIG, not a second hardcoded copy.

`a2mc_config.sh` / `a2mc_noncime_config.sh` export A2MC_MAX_SKIP_TESTING and A2MC_MAX_EXPERIMENTS,
and `orchestrator.py:3567-3571` reads both. This module used to carry its own 10s, which agreed with
the config only by coincidence ([[feedback_bind_derived_facts_to_their_source]]).

Author: Jing Tao with Claude
"""
import importlib.util
import json
import os

import pytest

SRC = "tools/check_workflow_state_offline.py"


def load():
    spec = importlib.util.spec_from_file_location("_chk", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def m(monkeypatch):
    monkeypatch.delenv("A2MC_MAX_SKIP_TESTING", raising=False)
    monkeypatch.delenv("A2MC_MAX_EXPERIMENTS", raising=False)
    return load()


def test_it_READS_the_env_var_rather_than_a_hardcoded_constant(m, monkeypatch):
    monkeypatch.setenv("A2MC_MAX_SKIP_TESTING", "6")
    v, note = m._limit_from_env("A2MC_MAX_SKIP_TESTING", 10)
    assert (v, note) == (6, None)


def test_a_config_value_ABOVE_the_fallback_is_honored_too(m, monkeypatch):
    """Guards against a min()/cap that would silently clamp a deliberate widening."""
    monkeypatch.setenv("A2MC_MAX_EXPERIMENTS", "25")
    assert m._limit_from_env("A2MC_MAX_EXPERIMENTS", 10)[0] == 25


def test_unset_falls_back_AND_says_so(m):
    v, note = m._limit_from_env("A2MC_MAX_SKIP_TESTING", 10)
    assert v == 10 and "not sourced" in note


@pytest.mark.parametrize("bad", ["nonsense", "", "  ", "3.5", "0", "-1"])
def test_a_junk_or_out_of_range_value_falls_back_and_never_raises(m, monkeypatch, bad):
    """A pre-commit hook must not die on a malformed config value."""
    monkeypatch.setenv("A2MC_MAX_SKIP_TESTING", bad)
    v, note = m._limit_from_env("A2MC_MAX_SKIP_TESTING", 10)
    assert v == 10 and note


def test_the_FALLBACKS_MATCH_what_the_shipped_configs_export(m):
    """A bare-environment run must agree with a sourced one, or the checker contradicts itself."""
    import re
    for cfg in ("a2mc_config.sh", "a2mc_noncime_config.sh"):
        text = open(cfg).read()
        for var, fallback in (("A2MC_MAX_SKIP_TESTING", m.FALLBACK_SKIP_TESTING_CAP),
                              ("A2MC_MAX_EXPERIMENTS", m.FALLBACK_MAX_EXPERIMENTS)):
            hit = re.search(rf"^export {var}=(\d+)", text, re.M)
            assert hit, f"{cfg} no longer exports {var}"
            assert int(hit.group(1)) == fallback, (
                f"{cfg} exports {var}={hit.group(1)} but the fallback is {fallback}")


def _state(tmp_path, **over):
    d = json.load(open("use_cases/EcoSIM_BioCON/memory/workflow_state_offline_r03.json"))
    d.update(over)
    p = tmp_path / "s.json"
    p.write_text(json.dumps(d))
    return str(p)


def test_the_skip_testing_WARNING_tracks_the_configured_limit(m, monkeypatch, tmp_path):
    monkeypatch.setenv("A2MC_MAX_SKIP_TESTING", "2")
    m2 = load()
    _e, w = m2.check_one(_state(tmp_path, skip_testing_count=5))
    assert any("over the inner-loop limit (2)" in x for x in w)


def test_it_is_SILENT_when_the_count_is_within_the_configured_limit(m, monkeypatch, tmp_path):
    monkeypatch.setenv("A2MC_MAX_SKIP_TESTING", "10")
    m2 = load()
    _e, w = m2.check_one(_state(tmp_path, skip_testing_count=5))
    assert not [x for x in w if "inner-loop limit" in x]


def test_max_experiments_fallback_also_comes_from_the_env(m, monkeypatch, tmp_path):
    """resolve_max_experiments' FALLBACK path (state lacks the key) must read the config too."""
    monkeypatch.setenv("A2MC_MAX_EXPERIMENTS", "4")
    m2 = load()
    d = json.load(open("use_cases/EcoSIM_BioCON/memory/workflow_state_offline_r03.json"))
    d.pop("max_experiments", None)
    d.pop("phase6_decision", None)
    p = tmp_path / "n.json"
    p.write_text(json.dumps(d))
    assert m2.resolve_max_experiments(json.loads(p.read_text()))[0] == 4
