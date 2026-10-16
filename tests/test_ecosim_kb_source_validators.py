"""The EcoSIM knowledge-base validators must FAIL on the defects they exist for.

visibility: public
Author: Jing Tao with Claude on Perlmutter

Covers `tools/ecosim_param_source_map.py` (the source classifier the graph builder and both
validators share), `tools/check_ecosim_seed_citations.py` and `tools/check_ecosim_tested_params_in_kb.py`.
Every assertion here names a way the tool must go RED, because a validator only ever seen green is
not evidence (`feedback_a_check_that_cannot_fail`). Each case is a defect found while re-anchoring
the knowledge base to EcoSIM `cb243228` (2026-10-15):

  * RSRA's only `ncd_getvar` sits in `ReadPlantTraitsNC`, which nothing calls; a name-literal grep
    called it file-backed. The classifier must report a DEAD read.
  * The six bioaerosol fractions are read through a wrapper (`read_aerosol_vars(loc,'fAeroDOM',..)`)
    and the grid extents through `check_var` + `nf90_get_var`; a literal-`ncd_getvar` scan called
    all ten never read. The classifier must find them LIVE.
  * Seed citations written against an older commit resolve to the wrong routine or past the end of
    a file. The citation resolver must refuse both.
  * A tested parameter the model never reads, that the seed does not declare inert, must fail the
    tested-parameter check, while one the seed declares inert must pass.

Needs the EcoSIM checkout at the active profile's commit ($A2MC_MODEL_PATH); skipped without it.

The cb243228 re-anchor and the defects behind the dated notes above: `memory/dev_logs_adapterkit/20261015a_The_EcoSIM_Knowledge_Base_Moves_To_The_Binary_R2_Runs.md`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
PY = sys.executable

from tools.ecosim_param_source_map import (Source, active_ecosim_profile, file_reads,  # noqa: E402
                                           find_citations, resolve_citation, resolve_param)

MODEL = os.environ.get("A2MC_MODEL_PATH", "")
PROFILE, MS = active_ecosim_profile(REPO)
COMMIT = MS["model_commit_built"]


def _has_commit() -> bool:
    if not MODEL or not Path(MODEL, ".git").exists():
        return False
    r = subprocess.run(["git", "-C", MODEL, "cat-file", "-e", f"{COMMIT}^{{commit}}"],
                       capture_output=True)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _has_commit(),
                                reason=f"EcoSIM checkout with {COMMIT[:8]} not available")


@pytest.fixture(scope="module")
def src():
    return Source(MODEL, COMMIT)


@pytest.fixture(scope="module")
def reads(src):
    return file_reads(src)


# --- the source classifier ------------------------------------------------------------------

def test_dead_reader_is_not_a_read(src, reads):
    """RSRA is read only inside the uncalled ReadPlantTraitsNC."""
    e = resolve_param(src, "RSRA", reads)
    assert e["reads"], "the dead read itself must still be found"
    assert e["status"] == "dead-read", e["status"]


def test_live_table_reader_is_a_read(src, reads):
    """ARSRA, read by the live ReadPlantTraitTable, is the positive control for the case above."""
    e = resolve_param(src, "ARSRA", reads)
    assert e["status"] == "used", e["status"]


def test_read_if_present_is_conditional(src, reads):
    """SPOSC is read only when MicrobePars carries it (check_var guard)."""
    assert resolve_param(src, "SPOSC", reads)["conditional"] is True


@pytest.mark.parametrize("name", ["fAeroDOM", "fAeroMoss"])
def test_wrapper_read_is_found(reads, name):
    hits = reads.get(name) or []
    assert hits, f"{name} is read through read_aerosol_vars and the scan missed it"
    assert all(h["live"] and h["conditional"] for h in hits)
    assert all(h.get("via") == "read_aerosol_vars" for h in hits)


@pytest.mark.parametrize("name", ["NHW", "NVS"])
def test_check_var_nf90_read_is_found(reads, name):
    hits = [h for h in reads.get(name) or [] if h["routine"] == "SetMesh"]
    assert hits and hits[0]["live"], f"{name} is read in SetMesh with check_var + nf90_get_var"
    assert hits[0]["conditional"] is False, "a missing extent aborts (endrun), so the read is required"


def test_unread_file_variable_has_no_read(reads):
    """NCNG is in the grid file and survives in source only as a dummy-argument name."""
    assert "NCNG" not in reads


# --- the citation resolver ------------------------------------------------------------------

def _resolve(src, text):
    (cit,) = find_citations(text)
    return resolve_citation(src, cit)


def test_correct_citation_resolves(src):
    r = _resolve(src, "f90src/IOutils/readimod.F90:440 (readTopoNC)")
    assert not r["errors"], r["errors"]


def test_wrong_routine_is_an_error(src):
    r = _resolve(src, "f90src/IOutils/readimod.F90:440 (readsiteNC)")
    assert r["errors"], "a citation naming the wrong enclosing routine must fail"


def test_line_past_end_of_file_is_an_error(src):
    r = _resolve(src, "f90src/IOutils/readimod.F90:999999 (readTopoNC)")
    assert r["errors"]


def test_missing_file_is_an_error(src):
    r = _resolve(src, "f90src/IOutils/NoSuchFileMod.F90:10 (Nothing)")
    assert r["errors"]


# --- the two command-line validators, end to end on tiny inputs -----------------------------

def _run(args, tmp_path):
    env = dict(os.environ, A2MC_MODEL_PATH=MODEL)
    return subprocess.run([PY, *args], cwd=REPO, env=env, capture_output=True, text=True)


def _tiny_seed(tmp_path, code_location):
    seed = {"parameters": {"ALBS": {"category": "soil_and_site", "code_location": code_location}},
            "mechanisms": {"Ground_Radiation_Balance": {
                "code_reference": "f90src/HydroTherm/SurfPhys/SurfPhysMod.F90:525-529 (SoilSRFEnerbyBalanceM)"}}}
    p = tmp_path / "seed.yaml"
    p.write_text(yaml.safe_dump(seed))
    return p


def test_seed_citation_checker_passes_a_good_seed(tmp_path):
    seed = _tiny_seed(tmp_path, "f90src/IOutils/readimod.F90:440 (readTopoNC)")
    r = _run(["tools/check_ecosim_seed_citations.py", "--seed", str(seed)], tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_seed_citation_checker_fails_a_stale_citation(tmp_path):
    """The 2dea74d9-era line for this read was :393; at cb243228 that line is in another routine."""
    seed = _tiny_seed(tmp_path, "f90src/IOutils/readimod.F90:440 (SoilSRFEnerbyBalanceM)")
    r = _run(["tools/check_ecosim_seed_citations.py", "--seed", str(seed)], tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "E1/E2" in r.stdout


def _param_list(tmp_path, *names):
    p = tmp_path / "params.csv"
    p.write_text("name,lower,upper\n" + "".join(f"{n},0,1\n" for n in names))
    return p


def test_tested_param_check_fails_an_unread_parameter(tmp_path):
    """CHL4 is in the shipped sample plant file and in no .F90: testing it is testing nothing."""
    pl = _param_list(tmp_path, "CHL4")
    r = _run(["tools/check_ecosim_tested_params_in_kb.py", "--param-list", str(pl), "--only", "S1,G1"],
             tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "CHL4" in r.stdout and "S1" in r.stdout


def test_tested_param_check_accepts_a_declared_inert_parameter(tmp_path):
    """RSRA is not read either, but the seed DECLARES it inert and the graph refuses it a
    controls edge, so the knowledge base is right about it and the check must pass."""
    pl = _param_list(tmp_path, "RSRA")
    r = _run(["tools/check_ecosim_tested_params_in_kb.py", "--param-list", str(pl), "--only", "S1,G1,G2"],
             tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("text, lhs", [
    ("  IF(SoiBulkDensityt0_vr(L,NY,NX).LE.ZERO)SoilFracAsMacP_vr(L,NY,NX)=0.0_r8", "SoilFracAsMacP_vr"),
    ("  SoilBulkDensity_vr(L,NY,NX)=SoiBulkDensityt0_vr(L,NY,NX)", "SoilBulkDensity_vr"),
    ("  IF(a .EQ. b)THEN", None),
    ("  if (x > 0) call foo(a=1)", None),
    ("  a == b", None),
])
def test_assigned_lhs_never_reports_a_keyword(text, lhs):
    """A one-line IF assigns its body's variable, never `IF`: the bare pattern put `IF` and `if`
    among BKDSI's derived variables, and because those two sort equal case-insensitively the
    generated wiki page changed order between processes and could never pass its own W2 check."""
    from tools.ecosim_param_source_map import assigned_lhs
    assert assigned_lhs(text) == lhs
