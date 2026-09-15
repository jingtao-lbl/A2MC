"""`tools/promote_knowledge.py` — every refusal fires, and a sanctioned promotion works.

The gap this tool closes: the two-tier knowledge architecture documents a site-to-generic
promotion arrow, and verified 2026-08-25 that arrow had NO implementation — no tool, no
`MemoryManager` method, no skill step. `tools/promote_diagnostic_script.py` promotes scripts, not
knowledge.

Written failure-first (`feedback_a_check_that_cannot_fail`). The refusals are the substance: a
promotion tool that promotes anything asked of it would turn a site-specific finding into a
general claim nobody can re-judge, which is worse than having no tool at all.

THE DESTINATION IS THE CASE'S OWN MODEL (2026-09-11). Until then every promotion went to
`memory/gained_knowledge/`, the FATES store, whatever model the case ran. The tests at the bottom
pin the routing: a FATES case lands in the unprefixed store, an EcoSIM case in
`memory/ecosim/gained_knowledge/`, and every way of getting the model wrong is refused. All of them
use `--dry-run` or `--list`, so no test writes into the repository's knowledge base.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "promote_knowledge.py"
FATES_STORE = ROOT / "memory" / "gained_knowledge" / "discoveries.json"
ECOSIM_STORE = ROOT / "memory" / "ecosim" / "gained_knowledge" / "discoveries.json"


def make_site(tmp_path, discoveries, *, models=(), name="C"):
    """A case dir with a site store; `models` writes one config file per declared A2MC_MODEL."""
    site = tmp_path / name
    gk = site / "memory" / "gained_knowledge"
    gk.mkdir(parents=True, exist_ok=True)
    (gk / "discoveries.json").write_text(json.dumps({"discoveries": discoveries, "_comment": "x"}))
    for i, m in enumerate(models):
        (site / "config").mkdir(exist_ok=True)
        (site / "config" / f"case_config_{i}.sh").write_text(f'export A2MC_MODEL="{m}"\n')
    return site


def run(site, *args, env_extra=None):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), **(env_extra or {})}
    cmd = [sys.executable, str(TOOL), "--site-dir", str(site), *args]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env)
    return r.returncode, r.stdout + r.stderr


VERIFIED = {"carbon_gain_synergy": {
    "description": "survival is a threshold in joint carbon-gain capacity, not a gradient",
    "mechanism": "clearing fewer than three of six thresholds gives P(alive)=0",
    "verified": True, "confidence": 0.9, "affects": ["plant_C"]}}

PROMOTE = ("--name", "carbon_gain_synergy", "--rationale", "threshold behaviour is general",
           "--dry-run")


# ---------------------------------------------------------------- the refusals

def test_P1_an_unknown_discovery_is_refused(tmp_path):
    code, out = run(make_site(tmp_path, VERIFIED), "--name", "nope", "--rationale", "r")
    assert code == 2 and "not in the site store" in out


def test_P3_an_unverified_discovery_is_refused(tmp_path):
    d = {"guess": {"description": "d", "mechanism": "m", "verified": False, "confidence": 0.4}}
    code, out = run(make_site(tmp_path, d), "--name", "guess", "--rationale", "r", "--dry-run")
    assert code == 2 and "not marked verified" in out


def test_P3_can_be_overridden_deliberately(tmp_path):
    d = {"guess": {"description": "d", "mechanism": "m", "verified": False, "confidence": 0.4}}
    code, out = run(make_site(tmp_path, d), "--name", "guess",
                    "--rationale", "corroborated at two other sites", "--allow-unverified",
                    "--dry-run")
    assert code == 0, out


def test_P4_a_promotion_without_a_rationale_is_refused(tmp_path):
    code, out = run(make_site(tmp_path, VERIFIED), "--name", "carbon_gain_synergy")
    assert code == 2 and "rationale is required" in out


def test_P5_an_empty_site_store_is_refused(tmp_path):
    code, out = run(make_site(tmp_path, {}), "--list")
    assert code == 2 and "nothing to promote" in out


def test_an_unresolvable_case_is_refused(tmp_path):
    """Refusing to guess which case's knowledge would enter the SHARED store."""
    r = subprocess.run([sys.executable, str(TOOL), "--list"], capture_output=True, text=True,
                       cwd=ROOT, env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())})
    assert r.returncode != 0 and "cannot resolve the case" in (r.stdout + r.stderr)


# ---------------------------------------------------------------- the sanctioned path

def test_list_shows_verified_and_unverified(tmp_path):
    d = dict(VERIFIED)
    d["hunch"] = {"description": "d", "mechanism": "m", "verified": False}
    code, out = run(make_site(tmp_path, d), "--list")
    assert code == 0, out
    assert "verified" in out and "UNVERIFIED" in out


def test_a_dry_run_writes_nothing_and_says_so(tmp_path):
    before = FATES_STORE.read_text() if FATES_STORE.is_file() else None
    code, out = run(make_site(tmp_path, VERIFIED), *PROMOTE)
    assert code == 0, out
    assert "DRY RUN" in out
    after = FATES_STORE.read_text() if FATES_STORE.is_file() else None
    assert before == after, "a dry run must not touch the model store"


def test_confidence_is_capped_on_promotion(tmp_path):
    """One site is ONE observation of generality. Carrying 0.9 forward would assert the same
    certainty about a strictly broader claim than the evidence supports."""
    code, out = run(make_site(tmp_path, VERIFIED), *PROMOTE)
    assert code == 0, out
    assert "0.9 -> 0.7" in out, out


def test_promotion_COPIES_and_leaves_the_site_entry_intact(tmp_path):
    """The site store stays the record of where the finding came from."""
    site = make_site(tmp_path, VERIFIED)
    src = site / "memory" / "gained_knowledge" / "discoveries.json"
    before = src.read_text()
    run(site, *PROMOTE)
    assert src.read_text() == before


# ---------------------------------------------------------------- the destination is the case's model

def test_a_fates_case_promotes_into_the_unprefixed_store(tmp_path):
    """A case whose config declares no model is a FATES case, exactly as sourcing it would be."""
    code, out = run(make_site(tmp_path, VERIFIED), *PROMOTE)
    assert code == 0, out
    assert "to   : memory/gained_knowledge/discoveries.json" in out, out


def test_an_ecosim_case_promotes_into_the_ecosim_store_not_fates(tmp_path):
    """THE DEFECT. Before 2026-09-11 this printed `to   : memory/gained_knowledge/...`."""
    fates_before, ecosim_before = FATES_STORE.read_text(), ECOSIM_STORE.read_text()
    code, out = run(make_site(tmp_path, VERIFIED, models=["ecosim"]), *PROMOTE)
    assert code == 0, out
    assert "to   : memory/ecosim/gained_knowledge/discoveries.json" in out, out
    assert (FATES_STORE.read_text(), ECOSIM_STORE.read_text()) == (fates_before, ecosim_before)


def test_list_names_the_model_store_it_compares_against(tmp_path):
    code, out = run(make_site(tmp_path, VERIFIED, models=["ecosim"]), "--list")
    assert code == 0, out
    assert "model store: ecosim, memory/ecosim/gained_knowledge/" in out, out


def test_P2_is_checked_against_the_cases_own_model_store(tmp_path):
    """A name already in the EcoSIM store is refused for an EcoSIM case."""
    payload = json.loads(ECOSIM_STORE.read_text())["discoveries"]
    existing = payload[0]["name"] if isinstance(payload, list) else next(iter(payload))
    d = {existing: {"description": "d", "mechanism": "m", "verified": True, "confidence": 0.8}}
    code, out = run(make_site(tmp_path, d, models=["ecosim"]),
                    "--name", existing, "--rationale", "r", "--dry-run")
    assert code == 2 and "already in the ecosim model store" in out, out


def test_P6_configs_that_declare_different_models_are_refused(tmp_path):
    code, out = run(make_site(tmp_path, VERIFIED, models=["ecosim", "pflotran"]), *PROMOTE)
    assert code == 2 and "cannot tell which model" in out, out


def test_P7_a_shell_model_that_disagrees_with_the_case_is_refused(tmp_path):
    code, out = run(make_site(tmp_path, VERIFIED, models=["ecosim"]), *PROMOTE,
                    env_extra={"A2MC_MODEL": "pflotran"})
    assert code == 2 and "config declares 'ecosim'" in out, out


def test_P7_an_agreeing_shell_model_is_fine(tmp_path):
    code, out = run(make_site(tmp_path, VERIFIED, models=["ecosim"]), *PROMOTE,
                    env_extra={"A2MC_MODEL": "ecosim"})
    assert code == 0, out


def test_P8_a_model_without_a_store_is_refused_and_nothing_is_created(tmp_path):
    """No FATES fallback, and no empty ATS store created in the repo."""
    code, out = run(make_site(tmp_path, VERIFIED, models=["ats"]), *PROMOTE)
    assert code == 2 and "has no knowledge store" in out, out
    assert not (ROOT / "memory" / "ats").exists()
