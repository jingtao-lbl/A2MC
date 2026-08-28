"""Tests for tools/config_graph.py -- the repo's own config graph.

Each test names a way the tool must FAIL, not a way it must pass
(auto-memory `feedback_a_check_that_cannot_fail`). The tool's job is to answer
"who SETS and who READS this variable"; the failures that matter are
misclassifying a consumer, counting a dev log as a consumer, and missing the
name-cluster that reveals two names for one quantity.

Author: Jing Tao with Claude
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

config_graph = pytest.importorskip("config_graph")


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """scan() resolves paths against config_graph.REPO -- point it at a temp tree."""
    monkeypatch.setattr(config_graph, "REPO", tmp_path)
    return tmp_path


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return rel


def test_shell_export_is_a_set_and_dollar_is_a_read(scratch):
    a = _write(scratch, "a2mc_config.sh", "export A2MC_THING=7\n")
    b = _write(scratch, "run.sh", 'echo "$A2MC_THING ${A2MC_THING:-9}"\n')
    g = config_graph.scan([a, b])
    assert len(g["A2MC_THING"]["set"]) == 1
    assert len(g["A2MC_THING"]["read"]) == 1


def test_shell_self_default_counts_as_set_not_read(scratch):
    """`FOO=${FOO:-x}` is BOTH textually; miscounting it as a read invents a
    phantom consumer and hides that the line is where the default is decided."""
    f = _write(scratch, "cfg.sh", "A2MC_N=${A2MC_N:-1000}\n")
    g = config_graph.scan([f])
    assert len(g["A2MC_N"]["set"]) == 1
    assert g["A2MC_N"]["read"] == [], "self-default must not also count as a read"


def test_python_environ_get_is_a_read_and_assignment_is_a_set(scratch):
    f = _write(scratch, "tools/x.py", (
        'import os\n'
        'v = os.environ.get("A2MC_PYVAR", "d")\n'
        'os.environ["A2MC_SETVAR"] = "1"\n'
        'os.environ.setdefault("A2MC_DEFVAR", "2")\n'
    ))
    g = config_graph.scan([f])
    assert len(g["A2MC_PYVAR"]["read"]) == 1
    assert g["A2MC_PYVAR"]["set"] == []
    assert len(g["A2MC_SETVAR"]["set"]) == 1
    assert len(g["A2MC_DEFVAR"]["set"]) == 1


def test_a_dev_log_mentioning_a_variable_is_not_a_consumer(scratch):
    """The failure this prevents: a grep-based answer drowning in its own history.
    A2MC_N_SAMPLES has more mentions under memory/ than in code."""
    code = _write(scratch, "a2mc_config.sh", "export A2MC_LOGGED=1\n")
    log = _write(scratch, "memory/dev_logs_adapterkit/20260822x_Note.md",
                 "We set $A2MC_LOGGED to 1 and read it everywhere.\n")
    g = config_graph.scan([code, log])
    assert len(g["A2MC_LOGGED"]["set"]) == 1
    assert g["A2MC_LOGGED"]["read"] == [], "a log mention must not become a reader"
    assert len(g["A2MC_LOGGED"]["record"]) == 1, "but it must still be RECORDED"


def test_read_but_never_set_is_detectable(scratch):
    """The class the 1000 belonged to: a default quietly in force because no
    config overrides it. If this shape is invisible, --orphans reports nothing."""
    f = _write(scratch, "tools/y.py", 'os.environ.get("A2MC_ORPHAN")\n')
    g = config_graph.scan([f])
    unset = [v for v, e in g.items() if e["read"] and not e["set"]]
    assert "A2MC_ORPHAN" in unset


def test_name_cluster_reveals_two_names_for_one_quantity(scratch):
    """The exact query that would have settled 2026-08-22 in one command."""
    a = _write(scratch, "a2mc_config.sh", "export A2MC_N_SAMPLES=1000\n")
    b = _write(scratch, "scripts/reg.py", 'os.environ.get("A2MC_SOBOL_N_SAMPLES")\n')
    g = config_graph.scan([a, b])
    cluster = sorted(v for v in g if "N_SAMPLES" in v)
    assert cluster == ["A2MC_N_SAMPLES", "A2MC_SOBOL_N_SAMPLES"]
    # the lopsided ratio IS the signature: one set-never-read, one read-never-set
    assert len(g["A2MC_SOBOL_N_SAMPLES"]["set"]) == 0
    assert len(g["A2MC_SOBOL_N_SAMPLES"]["read"]) == 1


def test_a_site_config_is_code_but_a_site_log_is_a_record(scratch):
    """use_cases/ holds BOTH. Treating the whole tree as records would drop every
    site config -- which is where a round's N actually lives."""
    cfg = _write(scratch, "use_cases/S/config/s_config.sh", "export A2MC_SITEVAR=3\n")
    log = _write(scratch, "use_cases/S/memory/logs/note.md", "A2MC_SITEVAR was 3\n")
    g = config_graph.scan([cfg, log])
    assert len(g["A2MC_SITEVAR"]["set"]) == 1, "a site CONFIG must count as code"
    assert len(g["A2MC_SITEVAR"]["record"]) == 1, "a site LOG must count as a record"


# ---------------------------------------------------------------------------------------------
# The repo's own `_env("A2MC_FOO", ...)` helper is a READ.
#
# THE UNDER-DETECTION THIS PINS (2026-08-23). READ_PY matched os.environ.get / os.environ[...] /
# getenv only, so a variable read exclusively through the `_env` wrapper reported "SET but never
# READ -- dead, or read by something outside the repo". Under-detection is the worst failure mode
# for this tool: its whole job is to answer "what consumes this", and a confident "nothing" is
# worse than no answer at all.
#
# Caught when a newly added A2MC_ROUND_CONFIG reported read:0 in the same commit that
# demonstrably read it. Measured impact was ONE variable, because the other 60 `_env` call sites
# name variables that are also read via os.environ somewhere else -- narrow, but the failure mode
# is the dangerous one, so it is pinned rather than left to luck.

def test_the_env_helper_counts_as_a_read():
    assert config_graph.READ_PY.findall('x = _env("A2MC_ROUND_CONFIG", required=False)') == ["A2MC_ROUND_CONFIG"]
    assert config_graph.READ_PY.findall('    y = _env("A2MC_USE_CASE_DIR")') == ["A2MC_USE_CASE_DIR"]


def test_the_original_read_forms_still_match():
    """Guard the other direction: widening the pattern must not drop what it already caught."""
    for src, want in (
            ('os.environ.get("A2MC_N_SAMPLES", "1000")', "A2MC_N_SAMPLES"),
            ('os.environ["A2MC_OUTPUT_DIR"]', "A2MC_OUTPUT_DIR"),
            ('getenv("A2MC_MODEL_PATH")', "A2MC_MODEL_PATH")):
        assert config_graph.READ_PY.findall(src) == [want], src


def test_a_bare_word_ending_in_env_is_not_a_read():
    """`\\b_env\\(` must not swallow e.g. `parse_env("A2MC_FOO")`, a different function."""
    assert config_graph.READ_PY.findall('parse_env("A2MC_SOMETHING")') == []
