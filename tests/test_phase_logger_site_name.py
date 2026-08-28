"""PhaseLogger must not head an adapter model's logs `**Site:** Unknown`.

Only the FATES site configs export A2MC_SITE_NAME; every EcoSIM and PFLOTRAN config exports
A2MC_SITE_CONFIG and not A2MC_SITE_NAME, so the old two-source lookup fell through to the literal
'Unknown' for every adapter case. Measured 2026-08-20: 88 of 126 committed EcoSIM_BioCON logs.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.phase_logger import PhaseLogger  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for v in ("A2MC_SITE_NAME", "A2MC_USE_CASE_DIR", "A2MC_AGENT_MODE"):
        monkeypatch.delenv(v, raising=False)


def test_explicit_argument_wins(tmp_path):
    lg = PhaseLogger(site_dir=str(tmp_path / "EcoSIM_BioCON"), site_name="Explicit")
    assert lg.site_name == "Explicit"


def test_env_var_wins_over_directory(tmp_path, monkeypatch):
    """The FATES path must be untouched: Kougarok stays 'Kougarok', not its directory name."""
    monkeypatch.setenv("A2MC_SITE_NAME", "Kougarok")
    lg = PhaseLogger(site_dir=str(tmp_path / "ELM-FATES_Kougarok"))
    assert lg.site_name == "Kougarok"


@pytest.mark.parametrize("case", ["EcoSIM_BioCON", "EcoSIM_Lusignan", "PFLOTRAN_miniLEO"])
def test_adapter_case_falls_back_to_the_directory_name(tmp_path, case):
    """THE BUG: no A2MC_SITE_NAME is exported by any adapter config."""
    lg = PhaseLogger(site_dir=str(tmp_path / case))
    assert lg.site_name == case
    assert lg.site_name != "Unknown"


def test_site_dir_from_env_also_yields_a_name(tmp_path, monkeypatch):
    d = tmp_path / "EcoSIM_BioCON"
    d.mkdir()
    monkeypatch.setenv("A2MC_USE_CASE_DIR", str(d))
    lg = PhaseLogger()
    assert lg.site_name == "EcoSIM_BioCON"


def test_written_header_carries_the_resolved_name(tmp_path):
    lg = PhaseLogger(site_dir=str(tmp_path / "EcoSIM_BioCON"), agent_mode="offline")
    lg.set_iteration_context(0, calibration_round=3)
    p = lg.log_design(title="T", sampling_method="sobol", n_parameters=1, n_simulations=1)
    txt = Path(p).read_text()
    assert "**Site:** EcoSIM_BioCON" in txt
    assert "**Site:** Unknown" not in txt
