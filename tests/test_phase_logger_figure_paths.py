"""The offline figure link must resolve, and its alt text must be empty.

NEGATIVE CONTROL: each test names the pre-fix behaviour it would accept, so reverting
`PhaseLogger._figure_rel_dir` to the hardcoded `phase3_diagnosis` string turns these red.

Measured 2026-09-08 on EcoSIM_Lusignan R1b c13 iter09: an offline Phase-4 log embedded its figure
through `../../phase_results/phase3_diagnosis/`, which exists for no offline log, while the body's
own correctly-pathed embed of the SAME figure sat 96 lines above it. The evidence gate
(`check_offline_log_evidence.py`) passed the file, so nothing caught it.
"""
import os
import re
from pathlib import Path

import pytest

from tools.phase_logger import PhaseLogger


@pytest.fixture
def site(tmp_path, monkeypatch):
    d = tmp_path / "use_cases" / "EcoSIM_Test"
    (d / "memory" / "logs").mkdir(parents=True)
    (d / "memory" / "phase_results").mkdir(parents=True)
    monkeypatch.setenv("A2MC_AGENT_MODE", "offline")
    monkeypatch.delenv("A2MC_SESSION_ID", raising=False)
    return d


def _logger(site):
    lg = PhaseLogger(site_dir=str(site), agent_mode="offline")
    lg.set_iteration_context(iteration=2, calibration_round=1,
                             experiment_count=3, skip_testing_count=1)
    return lg


@pytest.mark.parametrize("phase", [3, 4])
def test_offline_figure_dir_points_at_the_paired_stem(site, phase):
    """The link must be ../phase_results/<the log's own stem>, not a phase-named folder."""
    lg = _logger(site)
    title = "A Title That Becomes The Stem"
    stem = lg.topic_stem(phase, title)
    got = lg._figure_rel_dir(phase, title)
    assert got == f"../phase_results/{stem}", got
    # The exact pre-fix value, which is what this test exists to reject. Asserting merely that
    # "phase3_diagnosis" is absent would be wrong: a phase-3 STEM legitimately contains it.
    assert got != "../../phase_results/phase3_diagnosis"


def test_offline_phase4_link_resolves_from_the_log(site):
    """Write a real log and check the emitted link resolves to the figure on disk."""
    lg = _logger(site)
    title = "Phase Four Figure Link"
    folder = lg.topic_artifact_dir(4, title)
    fig = folder / "R1_c03_thing.png"
    fig.write_bytes(b"\x89PNG\r\n\x1a\n")
    out = lg.log_hypothesis(title=title, hypothesis_name="H", mechanism="m",
                            parameters_to_modify=[], figure_paths=[fig.name])
    links = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", out.read_text())
    assert links, "no image embedded"
    alt, href = links[0]
    assert alt == "", f"alt text must be empty, got {alt!r}"
    assert (out.parent / href).resolve() == fig.resolve(), (
        f"link {href} does not resolve to the figure; from {out.parent}")


def test_online_path_is_unchanged(site, monkeypatch):
    """This branch only ever ADDS: the online string must be byte-identical to before."""
    lg = PhaseLogger(site_dir=str(site), agent_mode="online")
    monkeypatch.setenv("A2MC_SESSION_ID", "20260908_120000")
    assert lg._figure_rel_dir(4, "T") == "../../phase_results/20260908_120000/phase3_diagnosis"
    monkeypatch.delenv("A2MC_SESSION_ID")
    assert lg._figure_rel_dir(4, "T") == "../../phase_results/phase3_diagnosis"
