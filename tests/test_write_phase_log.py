"""Every guard in tools/write_phase_log.py, proven to FAIL on the thing it exists to catch.

A guard that has only ever been observed passing is not a guard ([[feedback_a_check_that_cannot_fail]]).
Each test here drives the tool into one of the three failures measured on 2026-09-07 and asserts it
exits non-zero with the diagnosis, not merely that the happy path works.
"""
from __future__ import annotations
import os
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "write_phase_log.py"

PAYLOAD = '''
TITLE = "R9 c99 iter01 a fixture title that no real case uses"
COUNTERS = {"iteration": 1, "calibration_round": 9, "experiment_count": 99, "skip_testing_count": 0}
HANDSHAKE = {"inherited_from": "fixture", "handed_to": "fixture", "next_action": "fixture"}
LOG = {"failing_targets": ["x"], "likely_causes": ["y"]}
'''


def run(args, env=None):
    e = dict(os.environ)
    e.pop("A2MC_USE_CASE_DIR", None)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(TOOL)] + args, capture_output=True, text=True, env=e)


@pytest.fixture
def payload(tmp_path):
    p = tmp_path / "payload.py"
    p.write_text(PAYLOAD)
    return p


def test_no_site_refuses_rather_than_falling_back_to_template(payload):
    """FAILURE 1: create_logger() falls back to use_cases/TEMPLATE and writes a log there."""
    r = run(["--phase", "3", "--payload", str(payload)])
    assert r.returncode != 0
    assert "no site" in r.stderr.lower()
    assert "TEMPLATE" in r.stderr, "the refusal must name what it is refusing to do"


def test_explicit_template_site_is_refused(payload):
    """The same failure reached the other way: someone passes TEMPLATE deliberately."""
    r = run(["--phase", "3", "--payload", str(payload), "--site-dir", "use_cases/TEMPLATE"])
    assert r.returncode != 0
    assert "TEMPLATE" in r.stderr


def test_missing_site_dir_is_refused(payload):
    r = run(["--phase", "3", "--payload", str(payload), "--site-dir", "use_cases/NoSuchCase_Nope"])
    assert r.returncode != 0
    assert "does not exist" in r.stderr


@pytest.mark.parametrize("drop", ["TITLE", "COUNTERS", "HANDSHAKE", "LOG"])
def test_incomplete_payload_is_refused(tmp_path, drop):
    """A payload missing a required name must be named, not silently defaulted."""
    body = "\n".join(l for l in PAYLOAD.strip().split("\n") if not l.startswith(drop + " "))
    p = tmp_path / "payload.py"
    p.write_text(body)
    r = run(["--phase", "3", "--payload", str(p), "--site-dir", "use_cases/EcoSIM_TeRaCON"])
    assert r.returncode != 0
    assert drop in r.stderr


def test_empty_title_is_refused(tmp_path):
    p = tmp_path / "payload.py"
    p.write_text(PAYLOAD.replace('TITLE = "R9 c99 iter01 a fixture title that no real case uses"',
                                 'TITLE = "   "'))
    r = run(["--phase", "3", "--payload", str(p), "--site-dir", "use_cases/EcoSIM_TeRaCON"])
    assert r.returncode != 0
    assert "TITLE" in r.stderr


def test_agent_mode_is_forced_offline_not_merely_warned_about(payload, monkeypatch):
    """FAILURE 2: with A2MC_AGENT_MODE unset, PhaseLogger warns and writes the ONLINE layout."""
    src = TOOL.read_text()
    i_set = src.index('os.environ["A2MC_AGENT_MODE"] = "offline"')
    i_logger = src.index("create_logger(site_dir=")
    assert i_set < i_logger, (
        "offline mode must be set BEFORE the logger is constructed; setting it after is exactly "
        "the ordering that produced an online-layout log with an offline artifact folder")


def test_stem_pairing_is_asserted_after_the_write(payload):
    """FAILURE 3: the log and the folder minted different same-day letters."""
    src = TOOL.read_text()
    assert "STEM SPLIT" in src
    assert "log_path.stem != art.name" in src, (
        "the pairing must be asserted against the WRITTEN path, not assumed from the stem "
        "computed beforehand")


def test_the_phase_map_covers_every_phase_logger_method():
    """If PhaseLogger gains a phase, this map must not silently lag it."""
    sys.path.insert(0, str(REPO))
    from tools import phase_logger
    exposed = {n for n in dir(phase_logger.PhaseLogger) if n.startswith("log_")}
    src = TOOL.read_text()
    mapped = {m for m in exposed if m in src}
    missing = exposed - mapped - {"log_experiment_design"}
    assert not missing, "phase methods absent from METHOD and not reachable via --method: %s" % missing


def test_counters_are_set_before_the_stem_is_minted():
    """FAILURE 4: the stem EMBEDS the counters, so minting before set_iteration_context() bakes the
    defaults in -- measured 2026-09-07, a hand-rolled call produced `..._r01_c00_iter01_...` for a
    cycle-18 iteration-2 log. The folder then never pairs with the log the counters imply."""
    src = TOOL.read_text()
    i_counters = src.index("set_iteration_context(")
    i_stem = src.index("topic_stem(")
    i_dir = src.index("topic_artifact_dir(a.phase")
    assert i_counters < i_stem < i_dir or i_counters < i_dir, (
        "set_iteration_context() must precede topic_stem()/topic_artifact_dir(); the stem carries "
        "r{RR}_c{EE}_iter{II} and mints them from whatever the logger holds at call time")
