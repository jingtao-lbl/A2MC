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


def test_unset_reads_the_CONFIG_rather_than_the_built_in_copy(m):
    """The contract changed 2026-09-06: unset means READ THE CONFIG, not use a copy of it.

    The built-in constant is a second copy of a number the shipped configs export, and it agreed
    with them by coincidence. When a round raised the cap, two live cases passed the old value and
    the SAME state files validated in a sourced shell and failed in the bare pre-commit one.
    """
    v, note = m._limit_from_env("A2MC_MAX_SKIP_TESTING", 10)
    assert isinstance(v, int) and v >= 1
    assert "read from" in note or "DISAGREES" in note, note


def test_the_built_in_fallback_survives_when_no_config_states_the_value(m, tmp_path, monkeypatch):
    """The last-resort constant must still work: a checkout with no machine config must not crash."""
    monkeypatch.setattr(m, "_CONFIG_FILES", ("no_such_config.sh",))
    v, note = m._limit_from_env("A2MC_MAX_SKIP_TESTING", 10)
    assert v == 10 and "not sourced" in note


def test_a_DISAGREEMENT_between_the_configs_is_reported_and_resolved_upward(m, tmp_path, monkeypatch):
    """Two configs, two values: take the LARGER and name both, because this limit gates a commit."""
    (tmp_path / "a2mc_config.sh").write_text("export A2MC_MAX_EXPERIMENTS=10\n")
    (tmp_path / "a2mc_noncime_config.sh").write_text("export A2MC_MAX_EXPERIMENTS=20\n")
    monkeypatch.setattr(m, "_CONFIG_ROOT", tmp_path)
    v, note = m._limit_from_config("A2MC_MAX_EXPERIMENTS")
    assert v == 20, (v, note)
    assert "DISAGREES" in note and "10" in note and "20" in note, note


def test_agreeing_configs_report_the_value_and_do_not_cry_disagreement(m, tmp_path, monkeypatch):
    """The negative control for the test above: agreement must NOT produce a disagreement note."""
    (tmp_path / "a2mc_config.sh").write_text("export A2MC_MAX_EXPERIMENTS=12\n")
    (tmp_path / "a2mc_noncime_config.sh").write_text("export A2MC_MAX_EXPERIMENTS=12\n")
    monkeypatch.setattr(m, "_CONFIG_ROOT", tmp_path)
    v, note = m._limit_from_config("A2MC_MAX_EXPERIMENTS")
    assert v == 12 and "DISAGREES" not in note, (v, note)


@pytest.mark.parametrize("bad", ["nonsense", "", "  ", "3.5", "0", "-1"])
def test_a_junk_or_out_of_range_value_falls_back_and_never_raises(m, monkeypatch, bad):
    """A pre-commit hook must not die on a malformed config value."""
    monkeypatch.setenv("A2MC_MAX_SKIP_TESTING", bad)
    v, note = m._limit_from_env("A2MC_MAX_SKIP_TESTING", 10)
    assert v == 10 and note


def test_a_bare_run_AGREES_with_a_sourced_one_for_every_shipped_config(m, monkeypatch):
    """The invariant that matters, restated so it survives the configs legitimately diverging.

    The old form asserted that BOTH configs export exactly the built-in fallback, which made a
    deliberate change to either one fail a test about a copy rather than about the contract. What
    must hold is that a bare-environment resolution equals what sourcing that config would give.
    """
    import re
    for cfg in ("a2mc_config.sh", "a2mc_noncime_config.sh"):
        text = open(cfg).read()
        for var in ("A2MC_MAX_SKIP_TESTING", "A2MC_MAX_EXPERIMENTS"):
            hit = re.search(rf"^export {var}=(\d+)", text, re.M)
            assert hit, f"{cfg} no longer exports {var}"
            monkeypatch.setenv(var, hit.group(1))
            sourced, _ = m._limit_from_env(var, 10)
            assert sourced == int(hit.group(1))
            monkeypatch.delenv(var)
            bare, note = m._limit_from_env(var, 10)
            assert bare >= int(hit.group(1)), (
                f"a bare run resolves {var}={bare} while {cfg} exports {hit.group(1)}: "
                f"a pre-commit hook would block work a sourced shell allows. note={note}")


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


# ---------------------------------------------------------------------------------------------
# set_phase6_decision's own limit. Added 2026-09-07, after it recorded "experiment_count 12 of 10"
# for an adapter case whose config exports 20 -- a ROUTING gate reading as exhausted eight cycles
# early. These fail if that default ever goes back to a literal.
# ---------------------------------------------------------------------------------------------

def _p6_state(tmp_path):
    """A minimal offline state on disk, loaded through the real class."""
    import importlib.util as _iu
    from pathlib import Path as _P
    src = _P(__file__).resolve().parents[1] / "tools" / "workflow_state_offline.py"
    s = _iu.spec_from_file_location("_wso_t", src)
    mod = _iu.module_from_spec(s)
    s.loader.exec_module(mod)
    site = tmp_path / "use_cases" / "X_Y"
    (site / "memory").mkdir(parents=True)
    st = mod.WorkflowStateOffline.load(site_dir=site, calibration_round=1)
    st.data["experiment_count"] = 12
    return mod, st


def test_phase6_decision_takes_its_limit_from_the_config_not_a_literal(tmp_path, monkeypatch):
    monkeypatch.delenv("A2MC_MAX_EXPERIMENTS", raising=False)
    mod, st = _p6_state(tmp_path)
    st.set_phase6_decision("rethink_6to3")
    mx = st.data["phase6_decision"]["max_experiments"]
    from_cfg, _ = mod.limit_from_config("A2MC_MAX_EXPERIMENTS")
    assert mx == from_cfg, (
        f"set_phase6_decision recorded max_experiments={mx} while the machine configs state "
        f"{from_cfg}. A hardcoded default here makes a Phase-6 routing gate disagree with the "
        f"online agent, which reads the same variable from the same configs.")
    assert mx > st.data["experiment_count"], (
        "the shipped non-CIME config exports 20 and this state is at cycle 12, so a correct "
        "lookup must leave cycles remaining; 10 would declare the round exhausted")


def test_the_environment_still_wins_over_the_config(tmp_path, monkeypatch):
    monkeypatch.setenv("A2MC_MAX_EXPERIMENTS", "7")
    _mod, st = _p6_state(tmp_path)
    st.set_phase6_decision("rethink_6to3")
    assert st.data["phase6_decision"]["max_experiments"] == 7


def test_an_explicit_argument_still_wins_over_both(tmp_path, monkeypatch):
    monkeypatch.setenv("A2MC_MAX_EXPERIMENTS", "7")
    _mod, st = _p6_state(tmp_path)
    st.set_phase6_decision("rethink_6to3", max_experiments=3)
    assert st.data["phase6_decision"]["max_experiments"] == 3


def test_a_junk_environment_value_falls_back_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("A2MC_MAX_EXPERIMENTS", "not-a-number")
    mod, st = _p6_state(tmp_path)
    st.set_phase6_decision("rethink_6to3")
    from_cfg, _ = mod.limit_from_config("A2MC_MAX_EXPERIMENTS")
    assert st.data["phase6_decision"]["max_experiments"] == from_cfg
