"""Every shipped site config auto-sources its machine config, so one `source` is enough.

WHY THIS EXISTS. `a2mc_config.sh` and `a2mc_noncime_config.sh` are the ONLY files that set
`A2MC_MAX_EXPERIMENTS`, `A2MC_MAX_SKIP_TESTING` and `A2MC_CONFIDENCE_THRESHOLD` --
`orchestrator.py` reads all three as its argparse defaults and no site or round config sets them.
A session that sourced only a site config therefore had none of them, silently. v2.306 put an
auto-source guard in all eleven site configs; nothing tested it, so it could regress the same way.

WRITTEN FAILURE-FIRST (`feedback_a_check_that_cannot_fail`). Each test names the mutation it
catches, and two are regressions against real errors:

  * `test_guard_still_loads_when_the_family_variable_is_pre_exported` -- the v2.306 guard shipped
    one day earlier with a SINGLE clause testing the family variable alone. That variable is not
    exclusively a machine-config artifact (the PFLOTRAN configs set it themselves), so a shell that
    had it exported would satisfy the guard, skip the load, and leave the limits unset: the
    original bug, reintroduced through its own fix.
  * `test_guard_skips_when_already_loaded_and_the_matcher_can_fire` -- the skip is asserted by a
    banner NOT appearing, and "absent" is the same observation as "my pattern is wrong". The
    control lives in the same test so it cannot be deleted separately.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The three the guard exists to protect, and the per-family discriminators it keys on.
LIMITS = ("A2MC_MAX_EXPERIMENTS", "A2MC_MAX_SKIP_TESTING", "A2MC_CONFIDENCE_THRESHOLD")
NONCIME = dict(machine="a2mc_noncime_config.sh", var="A2MC_HPC_MPI_RANKS",
               banner="A2MC non-CIME base configuration loaded")
CIME = dict(machine="a2mc_config.sh", var="A2MC_DIN_LOC_ROOT",
            banner="A2MC base configuration loaded")


def _tracked_site_configs():
    """Site configs on THIS BRANCH, not whatever is lying on disk.

    `--cached --others --exclude-standard` is the branch's own view plus not-yet-added files, so a
    NEW case is covered the moment it is written and a gitignored stray never is
    (`feedback_a_gate_must_measure_the_branch_not_the_disk`).
    """
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard",
         "use_cases/*/config/*.sh"],
        capture_output=True, text=True, cwd=ROOT, check=True).stdout.split()
    return sorted(out)


SITE_CONFIGS = _tracked_site_configs()


def clean_env(**extra):
    """The environment a fresh login shell has: no A2MC_ anything."""
    e = {k: v for k, v in os.environ.items()
         if not (k.startswith("A2MC_") or k.startswith("_A2MC_"))}
    e.update(extra)
    return e


PROBE = ('echo "${A2MC_MAX_EXPERIMENTS:-UNSET}|${A2MC_MAX_SKIP_TESTING:-UNSET}'
         '|${A2MC_CONFIDENCE_THRESHOLD:-UNSET}|${A2MC_HPC_MPI_RANKS:-UNSET}'
         '|${A2MC_DIN_LOC_ROOT:-UNSET}"')


def source(*paths, env=None, cwd=None):
    """Source the given scripts in order and report the five variables that matter."""
    script = "".join(f'source "{p}" >/dev/null 2>&1\n' for p in paths) + PROBE
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                       cwd=str(cwd or ROOT), env=env if env is not None else clean_env())
    keys = ("max_experiments", "max_skip_testing", "confidence", "mpi_ranks", "din_loc_root")
    return dict(zip(keys, r.stdout.strip().splitlines()[-1].split("|")))


def family_of(cfg_text):
    return CIME if "A2MC_DIN_LOC_ROOT:-" in cfg_text else NONCIME


# --------------------------------------------------------------------------------------------
# The enumeration itself, so nothing below can pass by testing an empty list.
# --------------------------------------------------------------------------------------------

def test_the_enumeration_is_not_empty():
    """A glob that matches nothing makes every parametrized test below vacuously green."""
    assert len(SITE_CONFIGS) >= 15, (
        f"expected at least the 15 known site configs, found {len(SITE_CONFIGS)}: {SITE_CONFIGS}")
    assert any("EcoSIM" in c for c in SITE_CONFIGS)
    assert any("FATES" in c or "Kougarok" in c for c in SITE_CONFIGS)
    assert any("PFLOTRAN" in c for c in SITE_CONFIGS)
    assert any("ATS" in c for c in SITE_CONFIGS)


# --------------------------------------------------------------------------------------------
# The contract: one source, three limits.
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cfg", SITE_CONFIGS)
def test_every_site_config_yields_the_three_loop_limits(cfg):
    """Catches: a config that never got the guard, or one whose guard stopped firing."""
    got = source(cfg)
    missing = [n for n, k in zip(LIMITS, ("max_experiments", "max_skip_testing", "confidence"))
               if got[k] == "UNSET"]
    assert not missing, (
        f"{cfg} left {missing} UNSET when sourced alone. orchestrator.py reads all three as its "
        f"argparse defaults and no site or round config sets them, so the auto-source guard at the "
        f"top of this file is what supplies them.")


@pytest.mark.parametrize("cfg", [
    "use_cases/EcoSIM_Lusignan/config/ecosim_lusignan_config.sh",
    "use_cases/PFLOTRAN_template/config/pflotran_template_config.sh",
    "use_cases/ELM-FATES_Kougarok/config/kougarok_config.sh",
])
def test_guard_still_loads_when_the_family_variable_is_pre_exported(cfg):
    """THE REGRESSION. A one-clause guard keyed on the family variable alone skips here.

    The PFLOTRAN configs set `A2MC_HPC_MPI_RANKS` themselves and `pflotran_minileo_config.sh`
    already warned in a comment about a stale shell-level export of it, so this is a shell state
    that occurs. The second clause (`A2MC_MAX_EXPERIMENTS`, set by both machine configs and by no
    site config) is what keeps the guard firing.
    """
    fam = family_of((ROOT / cfg).read_text())
    got = source(cfg, env=clean_env(**{fam["var"]: "999"}))
    assert got["max_experiments"] != "UNSET", (
        f"{cfg} skipped its machine config because {fam['var']} was already exported. That is the "
        f"one-clause guard's failure mode and the reason the second clause exists.")


@pytest.mark.parametrize("cfg", [
    "use_cases/EcoSIM_Lusignan/config/ecosim_lusignan_config.sh",
    "use_cases/ELM-FATES_Kougarok/config/kougarok_config.sh",
])
def test_guard_repairs_the_wrong_machine_config(cfg):
    """Sourcing the other family's machine config first must be corrected, not accepted."""
    text = (ROOT / cfg).read_text()
    fam = family_of(text)
    wrong = CIME["machine"] if fam is NONCIME else NONCIME["machine"]
    got = source(wrong, cfg)
    key = "din_loc_root" if fam is CIME else "mpi_ranks"
    assert got[key] != "UNSET", (
        f"{cfg} did not load {fam['machine']} after {wrong} was sourced by mistake; the family "
        f"variable {fam['var']} is still unset, so the wrong choice was accepted rather than repaired.")
    assert got["max_experiments"] != "UNSET"


@pytest.mark.parametrize("cfg", [
    "use_cases/EcoSIM_Lusignan/config/ecosim_lusignan_config.sh",
    "use_cases/ELM-FATES_Kougarok/config/kougarok_config.sh",
])
def test_guard_skips_when_already_loaded_and_the_matcher_can_fire(cfg):
    """The skip, PLUS the control that proves the skip was observed rather than mis-matched.

    Asserting a banner is absent is worthless on its own: a typo in the pattern produces the same
    green. So the same pattern is also run where the guard DOES load, and must be found there.
    """
    fam = family_of((ROOT / cfg).read_text())

    def banners(*paths):
        script = "".join(f'source "{p}"\n' for p in paths)
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                           cwd=str(ROOT), env=clean_env())
        return (r.stdout + r.stderr).count(fam["banner"])

    assert banners(cfg) >= 1, (
        f"CONTROL FAILED: the banner {fam['banner']!r} was not found even from a fresh shell, "
        f"where the guard certainly loads {fam['machine']}. The pattern is wrong, so the skip "
        f"assertion below would prove nothing. Fix the pattern before reading the next result.")
    n = banners(fam["machine"], cfg)
    assert n == 1, (
        f"expected exactly 1 {fam['machine']} banner when it is sourced explicitly and then {cfg} "
        f"runs, got {n}: 2 means the guard re-loaded it, 0 means neither load happened.")


# --------------------------------------------------------------------------------------------
# The mutation: remove the guard and the limits must go away.
# --------------------------------------------------------------------------------------------

GUARD = re.compile(
    r"# ---- Auto-source the MACHINE config if it is not already loaded -+\n"
    r".*?\n^fi$\n", re.S | re.M)


def _synthetic_case(tmp_path, guard_text):
    """A repo-shaped tree: <root>/a2mc_noncime_config.sh and <root>/use_cases/C/config/c.sh.

    The guard resolves the repo root as SCRIPT_DIR/../../.., so the depth is what makes this a
    faithful harness rather than a mock.
    """
    root = tmp_path / "repo"
    (root / "use_cases" / "Case" / "config").mkdir(parents=True)
    (root / "a2mc_noncime_config.sh").write_text(
        "export A2MC_HPC_MPI_RANKS=1\n"
        "export A2MC_MAX_EXPERIMENTS=10\n"
        "export A2MC_MAX_SKIP_TESTING=10\n"
        "export A2MC_CONFIDENCE_THRESHOLD=0.95\n")
    cfg = root / "use_cases" / "Case" / "config" / "case_config.sh"
    cfg.write_text(
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'export A2MC_USE_CASE_DIR="$(dirname "$SCRIPT_DIR")"\n'
        + guard_text
        + 'export A2MC_SITE_NAME="Case"\n')
    return root, cfg


def test_the_guard_is_what_supplies_the_limits(tmp_path):
    """Mutation: the SAME synthetic case with and without the guard block.

    Guard present -> limits set. Guard removed -> all three UNSET. If the second half ever passes,
    something other than the guard is supplying them and every test above is measuring the wrong
    thing.
    """
    real = (ROOT / "use_cases/EcoSIM_BioCON/config/ecosim_biocon_config.sh").read_text()
    m = GUARD.search(real)
    assert m, ("the guard block could not be found in the live BioCON config -- either it was "
               "removed (a real regression) or its header comment was reworded, in which case fix "
               "the GUARD pattern in this test")

    root, cfg = _synthetic_case(tmp_path, m.group(0))
    with_guard = source(cfg, cwd=root)
    assert with_guard["max_experiments"] == "10", with_guard

    cfg.write_text(GUARD.sub("", cfg.read_text()))
    without = source(cfg, cwd=root)
    assert [without[k] for k in ("max_experiments", "max_skip_testing", "confidence")] \
        == ["UNSET", "UNSET", "UNSET"], (
        f"removing the guard did NOT unset the loop limits ({without}); something else is "
        f"supplying them and these tests are not measuring the guard.")


def test_the_template_duplicates_stay_identical():
    """`use_cases/TEMPLATE/config/*` are byte-identical copies of the `*_template/config/` ones.

    Two files, one meaning: patch one and forget the other and a scaffolded case silently gets the
    older shape. Caught here rather than by a user.
    """
    pairs = [("EcoSIM_template/config/ecosim_template_config.sh", "TEMPLATE/config/ecosim_template_config.sh"),
             ("ELM-FATES_template/config/fates_template_config.sh", "TEMPLATE/config/fates_template_config.sh"),
             ("PFLOTRAN_template/config/pflotran_template_config.sh", "TEMPLATE/config/pflotran_template_config.sh")]
    for canon, dupe in pairs:
        a = (ROOT / "use_cases" / canon).read_bytes()
        b = (ROOT / "use_cases" / dupe).read_bytes()
        assert a == b, f"use_cases/{dupe} has drifted from use_cases/{canon}"
