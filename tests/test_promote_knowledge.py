"""`tools/promote_knowledge.py` — every refusal fires, and a sanctioned promotion works.

The gap this tool closes: the two-tier knowledge architecture documents a site-to-generic
promotion arrow, and verified 2026-08-25 that arrow had NO implementation — no tool, no
`MemoryManager` method, no skill step. `tools/promote_diagnostic_script.py` promotes scripts, not
knowledge.

Written failure-first (`feedback_a_check_that_cannot_fail`). The refusals are the substance: a
promotion tool that promotes anything asked of it would turn a site-specific finding into a
general claim nobody can re-judge, which is worse than having no tool at all.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "promote_knowledge.py"


def make_site(tmp_path, discoveries):
    gk = tmp_path / "C" / "memory" / "gained_knowledge"
    gk.mkdir(parents=True, exist_ok=True)
    (gk / "discoveries.json").write_text(json.dumps({"discoveries": discoveries, "_comment": "x"}))
    return tmp_path / "C"


def run(site, *args, generic=None):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home())}
    cmd = [sys.executable, str(TOOL), "--site-dir", str(site), *args]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env)
    return r.returncode, r.stdout + r.stderr


VERIFIED = {"carbon_gain_synergy": {
    "description": "survival is a threshold in joint carbon-gain capacity, not a gradient",
    "mechanism": "clearing fewer than three of six thresholds gives P(alive)=0",
    "verified": True, "confidence": 0.9, "affects": ["plant_C"]}}


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
    generic = ROOT / "memory" / "gained_knowledge" / "discoveries.json"
    before = generic.read_text() if generic.is_file() else None
    code, out = run(make_site(tmp_path, VERIFIED), "--name", "carbon_gain_synergy",
                    "--rationale", "threshold behaviour is not site-specific", "--dry-run")
    assert code == 0, out
    assert "DRY RUN" in out
    after = generic.read_text() if generic.is_file() else None
    assert before == after, "a dry run must not touch the generic store"


def test_confidence_is_capped_on_promotion(tmp_path):
    """One site is ONE observation of generality. Carrying 0.9 forward would assert the same
    certainty about a strictly broader claim than the evidence supports."""
    code, out = run(make_site(tmp_path, VERIFIED), "--name", "carbon_gain_synergy",
                    "--rationale", "threshold behaviour is not site-specific", "--dry-run")
    assert code == 0, out
    assert "0.9 -> 0.7" in out, out


def test_promotion_COPIES_and_leaves_the_site_entry_intact(tmp_path):
    """The site store stays the record of where the finding came from."""
    site = make_site(tmp_path, VERIFIED)
    src = site / "memory" / "gained_knowledge" / "discoveries.json"
    before = src.read_text()
    run(site, "--name", "carbon_gain_synergy", "--rationale", "general", "--dry-run")
    assert src.read_text() == before
