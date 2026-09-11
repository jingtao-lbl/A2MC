"""`--site` is repeatable, and the pre-commit hook scopes to the cases with staged files.

NEGATIVE CONTROL: reverting `--site` to `action=None` (a single value) turns
`test_two_sites_are_both_scanned` red; reverting the hook block to an unscoped invocation turns
`test_hook_scopes_to_staged_sites` and `test_hook_skips_when_no_case_file_is_staged` red.

WHY THIS EXISTS. Run repo-wide, this check prints OTHER cases' stem names into every commit. In a
shared clone those belong to campaigns the committer is not working on, and it is not only noise:
measured 2026-09-08, a Phase-5 experiment in one case was named with a NUMBERING CONVENTION
belonging to another, whose stems this warning had put in front of the author on about a dozen
consecutive commits.

THE FRESH-CLONE CASE, which is the one worth stating. A user who has just cloned A2MC has only the
shipped templates under `use_cases/` and no case of their own. Nothing they commit touches a case
until they create one, so the check is SKIPPED until then and first appears on the first commit
into their OWN case, which is exactly when its advice applies. Run repo-wide it would instead have
greeted them on their very first commit with findings about someone else's campaign.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "check_case_script_tier.py"
HOOK = ROOT / ".githooks" / "pre-commit"


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args],
                          cwd=ROOT, capture_output=True, text=True)


def test_site_is_repeatable():
    """The option must ACCEPT two values; a single-value option errors or keeps only the last."""
    r = run("--site", "EcoSIM_Lusignan", "--site", "EcoSIM_TeRaCON")
    assert r.returncode in (0, 1), r.stderr
    assert "error:" not in r.stderr.lower(), r.stderr


def test_two_sites_are_both_scanned():
    """Both named cases appear in the scope line or the findings; neither is silently dropped."""
    r = run("--site", "EcoSIM_Lusignan", "--site", "EcoSIM_TeRaCON")
    out = r.stdout
    assert "EcoSIM_Lusignan" in out and "EcoSIM_TeRaCON" in out, out


def test_scoping_narrows_the_result():
    """A scoped run must not report findings from a case outside the scope."""
    wide = run()
    narrow = run("--site", "EcoSIM_Lusignan")
    if wide.returncode == 0:
        pytest.skip("no findings anywhere; scoping cannot be observed")
    others = {m for m in re.findall(r"^    (\w+)/", wide.stdout, re.M)} - {"EcoSIM_Lusignan"}
    if not others:
        pytest.skip("findings exist only in the scoped case")
    for site in others:
        assert site not in narrow.stdout, (
            f"{site} leaked into a run scoped to EcoSIM_Lusignan:\n{narrow.stdout}")


def test_unscoped_still_scans_everything():
    """The default must stay repo-wide: round-close housekeeping depends on it."""
    r = run()
    assert "every case" in r.stdout or r.returncode == 1, r.stdout


def test_hook_scopes_to_staged_sites():
    """The hook must derive --site from the staged paths rather than calling the tool bare."""
    t = HOOK.read_text()
    block = t[t.index("check_case_script_tier.py -- a script reused"):]
    block = block[:block.index("\n# (") if "\n# (" in block else len(block)]
    assert "--site" in block, "the hook does not scope the check"
    assert "diff --cached --name-only" in block, "the hook does not read the staged paths"
    assert re.search(r"sed -n 's\|\^use_cases/", block), \
        "the hook does not extract the case name from a staged path"


def test_hook_skips_when_no_case_file_is_staged():
    """No staged case file -> no invocation. This is the fresh-clone answer."""
    t = HOOK.read_text()
    block = t[t.index("check_case_script_tier.py -- a script reused"):]
    block = block[:block.index("\n# (") if "\n# (" in block else len(block)]
    assert re.search(r"\$\{#TIER_SITES\[@\]\}\s*-gt\s*0", block), \
        "the hook does not guard on a non-empty site list, so a commit touching no case would " \
        "still run the check repo-wide"


def test_the_extractor_handles_the_real_shapes():
    """The sed that turns staged paths into case names, exercised on real path shapes."""
    paths = "\n".join([
        "use_cases/EcoSIM_Lusignan/memory/logs/x.md",
        "use_cases/EcoSIM_TeRaCON/reports/y/z.md",
        "use_cases/TEMPLATE/memory/gained_knowledge/parameters.json",
        "tools/check_case_script_tier.py",
        "CLAUDE.md",
    ])
    r = subprocess.run(["sed", "-n", r"s|^use_cases/\([^/]*\)/.*|\1|p"],
                       input=paths, capture_output=True, text=True)
    got = sorted(set(r.stdout.split()))
    assert got == ["EcoSIM_Lusignan", "EcoSIM_TeRaCON", "TEMPLATE"], got


def test_no_case_paths_yields_no_sites():
    """The fresh-clone / tools-only commit: the extractor yields nothing at all."""
    paths = "tools/foo.py\nCLAUDE.md\nREADME.md\n"
    r = subprocess.run(["sed", "-n", r"s|^use_cases/\([^/]*\)/.*|\1|p"],
                       input=paths, capture_output=True, text=True)
    assert r.stdout.strip() == "", r.stdout
