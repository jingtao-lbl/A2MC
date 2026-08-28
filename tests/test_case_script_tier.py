"""The three script tiers: template in scripts/, instance in phase_results/{stem}/, library in tools/.

Every test names a way the check must FIRE or must NOT ([[feedback_a_check_that_cannot_fail]]).
The check is measured against a REAL repo scan, so these drive it through a temp git repo instead of
mocking, which is what makes the git-index enumeration itself covered.

Author: Jing Tao with Claude
"""
import importlib.util
import subprocess

import pytest

SRC = "tools/check_case_script_tier.py"


def load(repo):
    spec = importlib.util.spec_from_file_location("_tier", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.REPO = repo
    return m


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def put(repo, rel, body="print('x')\n"):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


SITE = "use_cases/EcoSIM_Demo"
PR = f"{SITE}/memory/phase_results"


def test_it_FIRES_on_the_same_script_in_two_stem_folders_with_no_template(repo):
    put(repo, f"{PR}/20260901a_phase5_testing_r03_c01_x/analyze.py")
    put(repo, f"{PR}/20260901b_phase6_refinement_r03_c01_x/analyze.py")
    f, _ = load(repo).scan()
    assert len(f) == 1 and f[0]["name"] == "analyze.py"


def test_it_reports_BYTE_IDENTICAL_separately_from_diverged(repo):
    put(repo, f"{PR}/20260901a_phase5_testing_r03_c01_x/analyze.py", "A\n")
    put(repo, f"{PR}/20260901b_phase6_refinement_r03_c01_x/analyze.py", "A\n")
    assert load(repo).scan()[0][0]["identical"] is True
    put(repo, f"{PR}/20260901b_phase6_refinement_r03_c01_x/analyze.py", "B\n")
    assert load(repo).scan()[0][0]["identical"] is False


def test_it_is_SILENT_when_the_template_tier_IS_used(repo):
    """The whole point: duplication is fine once a template exists to adapt from."""
    put(repo, f"{SITE}/scripts/analyze.py")
    put(repo, f"{PR}/20260901a_phase5_testing_r03_c01_x/analyze.py")
    put(repo, f"{PR}/20260901b_phase6_refinement_r03_c01_x/analyze.py")
    f, _ = load(repo).scan()
    assert f == []


def test_a_template_in_ANOTHER_case_does_not_excuse_this_one(repo):
    """Tiers are per-case; a neighbouring case's template is not this case's."""
    put(repo, "use_cases/EcoSIM_Other/scripts/analyze.py")
    put(repo, f"{PR}/20260901a_phase5_testing_r03_c01_x/analyze.py")
    put(repo, f"{PR}/20260901b_phase6_refinement_r03_c01_x/analyze.py")
    assert len(load(repo).scan()[0]) == 1


def test_a_script_used_ONCE_is_not_flagged(repo):
    """The trigger is the SECOND use. A single instance is the correct first-use state."""
    put(repo, f"{PR}/20260901a_phase5_testing_r03_c01_x/analyze.py")
    assert load(repo).scan()[0] == []


def test_it_is_NON_RETROACTIVE_and_counts_the_exempt(repo):
    put(repo, f"{PR}/20260717p_phase5_testing_r01_c04_x/analyze.py")
    put(repo, f"{PR}/20260717q_phase6_refinement_r01_c04_x/analyze.py")
    f, exempt = load(repo).scan()
    assert f == [] and exempt == 1


def test_a_group_is_judged_by_its_NEWEST_member(repo):
    """Copying an OLD script into a NEW phase today is a new violation, not grandfathered."""
    put(repo, f"{PR}/20260717p_phase5_testing_r01_c04_x/analyze.py")
    put(repo, f"{PR}/20260901b_phase6_refinement_r03_c01_x/analyze.py")
    f, exempt = load(repo).scan()
    assert len(f) == 1 and exempt == 0


def test_untracked_files_are_STILL_scanned(repo):
    """A script written this session is not committed yet, and is exactly the one worth catching."""
    put(repo, f"{PR}/20260901a_phase5_testing_r03_c01_x/analyze.py")
    put(repo, f"{PR}/20260901b_phase6_refinement_r03_c01_x/analyze.py")
    # nothing is git-added on purpose
    assert len(load(repo).scan()[0]) == 1


def test_the_site_filter_restricts_scope(repo):
    put(repo, f"{PR}/20260901a_phase5_testing_r03_c01_x/analyze.py")
    put(repo, f"{PR}/20260901b_phase6_refinement_r03_c01_x/analyze.py")
    m = load(repo)
    assert len(m.scan("EcoSIM_Demo")[0]) == 1
    assert m.scan("EcoSIM_Nonexistent")[0] == []


def test_non_python_files_are_ignored(repo):
    put(repo, f"{PR}/20260901a_phase5_testing_r03_c01_x/notes.md", "x")
    put(repo, f"{PR}/20260901b_phase6_refinement_r03_c01_x/notes.md", "x")
    assert load(repo).scan()[0] == []
