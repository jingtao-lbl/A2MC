"""A sourced config must find its own location under zsh as well as bash.

visibility: public

Every machine and site config derives its paths from where the file itself lives. `BASH_SOURCE` is
a bash builtin and is EMPTY under zsh (the macOS login shell), so a bare `${BASH_SOURCE[0]}` makes
every derived path silently become the current directory: `A2MC_ROOT` points wherever `source` was
typed, `A2MC_SITE_CONFIG` becomes a directory, and the config's `mkdir -p "${A2MC_ROOT}/tmp"` litters
that directory. Nothing fails. The portable form is `${BASH_SOURCE[0]:-$0}`: when zsh sources a file,
`$0` is that file, and when bash sources one, `BASH_SOURCE[0]` is always set, so bash is unchanged.

Two halves. The static one needs no zsh and catches the construction wherever the suite runs. The
behavioural one sources every config for real, under both shells, from an unrelated directory.

Files are enumerated from git, not the disk, so an untracked stray config neither passes nor fails
the branch.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PATTERNS = ["a2mc_config.sh", "a2mc_noncime_config.sh", "use_cases/*/config/*.sh"]
BARE = re.compile(r"\$\{BASH_SOURCE\[0\]\}")
VARS = ["A2MC_ROOT", "A2MC_USE_CASE_DIR", "A2MC_SITE_CONFIG", "A2MC_ROUND_CONFIG"]


def _configs():
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--cached", "--others", "--exclude-standard", "--"]
        + PATTERNS, capture_output=True, text=True, check=True).stdout.split()
    return sorted(p for p in out if "BASH_SOURCE" in (REPO / p).read_text(errors="replace"))


CONFIGS = _configs()


def test_there_is_something_to_check():
    assert "a2mc_noncime_config.sh" in CONFIGS, CONFIGS


@pytest.mark.parametrize("rel", CONFIGS)
def test_no_bare_BASH_SOURCE_in_a_sourced_config(rel):
    bad = [i for i, line in enumerate((REPO / rel).read_text().splitlines(), 1)
           if BARE.search(line) and not line.lstrip().startswith("#")]
    assert not bad, "%s: bare ${BASH_SOURCE[0]} on line(s) %s -- use ${BASH_SOURCE[0]:-$0}" % (rel, bad)


def _source(shell, rel, cwd):
    env = {k: os.environ[k] for k in ("HOME", "PATH", "USER", "NERSC_HOST") if k in os.environ}
    probe = "source '%s' >/dev/null 2>&1; printf '%s' %s" % (
        REPO / rel, "|".join(["%s"] * len(VARS)), " ".join('"$%s"' % v for v in VARS))
    r = subprocess.run([shell, "-c", probe], cwd=str(cwd), env=env, capture_output=True,
                       text=True, timeout=60)
    return dict(zip(VARS, r.stdout.split("|")))


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed here")
@pytest.mark.parametrize("rel", CONFIGS)
def test_bash_and_zsh_resolve_the_same_paths_from_an_unrelated_directory(rel, tmp_path):
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    in_bash, in_zsh = _source("bash", rel, cwd), _source("zsh", rel, cwd)
    assert in_zsh == in_bash, "%s resolves differently under zsh:\n bash %s\n zsh  %s" % (
        rel, in_bash, in_zsh)
    if in_zsh.get("A2MC_ROOT"):
        assert os.path.realpath(in_zsh["A2MC_ROOT"]) == os.path.realpath(str(REPO)), in_zsh
    if in_zsh.get("A2MC_SITE_CONFIG"):
        assert os.path.isfile(in_zsh["A2MC_SITE_CONFIG"]), in_zsh
    assert not (cwd / "tmp").exists(), "sourcing %s created tmp/ in the working directory" % rel
