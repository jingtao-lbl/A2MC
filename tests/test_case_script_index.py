"""tools/case_script_index.py: a case's template index is derived from the templates, and checked.

visibility: public

Each test builds a throwaway git repository holding one case. The first is the positive control: a
case whose README has no index, while it holds a template, must be reported -- otherwise every
"current" below is vacuous.
"""
import subprocess

from tools import case_script_index as I


def _repo(tmp_path, files):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    case = tmp_path / "use_cases" / "Model_Case"
    for name, text in files.items():
        p = case / "scripts" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return case


PY = '"""TEMPLATE: draw the thing.\n\nMore.\n"""\n'
SH = "#!/bin/bash\n# Watch the other thing.\nset -e\n"


def test_missing_index_is_reported(tmp_path):
    case = _repo(tmp_path, {"plot_a.py": PY, "README.md": "# scripts\n"})
    assert I.check(case, tmp_path)                     # fails if a missing index passes


def test_write_then_check_is_current_and_idempotent(tmp_path):
    case = _repo(tmp_path, {"plot_a.py": PY, "watch.sh": SH, "README.md": "# scripts\n\nhand text\n"})
    I.write(case, tmp_path)
    once = (case / "scripts" / "README.md").read_text()
    assert I.check(case, tmp_path) == []
    I.write(case, tmp_path)
    assert (case / "scripts" / "README.md").read_text() == once
    assert "hand text" in once                          # text outside the markers is kept
    assert "| `plot_a.py` | draw the thing. |" in once  # TEMPLATE prefix stripped, first line only
    assert "| `watch.sh` | Watch the other thing. |" in once


def test_new_template_makes_index_stale(tmp_path):
    case = _repo(tmp_path, {"plot_a.py": PY, "README.md": "# scripts\n"})
    I.write(case, tmp_path)
    (case / "scripts" / "plot_b.py").write_text(PY)
    assert any("plot_b.py" in p for p in I.check(case, tmp_path))


def test_removed_template_makes_index_stale(tmp_path):
    case = _repo(tmp_path, {"plot_a.py": PY, "plot_b.py": PY, "README.md": "# scripts\n"})
    I.write(case, tmp_path)
    (case / "scripts" / "plot_b.py").unlink()
    assert any("plot_b.py" in p for p in I.check(case, tmp_path))


def test_changed_summary_makes_index_stale(tmp_path):
    case = _repo(tmp_path, {"plot_a.py": PY, "README.md": "# scripts\n"})
    I.write(case, tmp_path)
    (case / "scripts" / "plot_a.py").write_text('"""Draw something else."""\n')
    assert I.check(case, tmp_path)


def test_template_without_summary_is_reported(tmp_path):
    case = _repo(tmp_path, {"bare.py": "x = 1\n", "README.md": "# scripts\n"})
    I.write(case, tmp_path)
    assert any("no summary line" in p for p in I.check(case, tmp_path))


def test_ignored_file_is_not_a_template(tmp_path):
    case = _repo(tmp_path, {"plot_a.py": PY, "scratch.py": PY, "README.md": "# scripts\n"})
    (tmp_path / ".gitignore").write_text("scratch.py\n")
    assert [p.name for p in I.templates(case, tmp_path)] == ["plot_a.py"]


# ---- case_template/: every run file is listed; a summary is shown where present, never required ----

def _runs(tmp_path, files):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    case = tmp_path / "use_cases" / "Model_Case"
    (case / "case_template").mkdir(parents=True)
    (case / "case_template" / "README.md").write_text("# run files\n\n## Skills\n\nx\n\n## Traps\n\ny\n")
    for name, text in files.items():
        (case / "case_template" / name).write_text(text)
    return case


LAUNCHER = "#!/bin/bash\n#SBATCH --qos=regular\n# ======\n# Packed runner, many cases per node.\nset -e\n"


def test_case_template_new_run_file_makes_index_stale(tmp_path):
    case = _runs(tmp_path, {"submit.sh": LAUNCHER})
    I.write(case, tmp_path, ["case_template"])
    (case / "case_template" / "run.nml").write_text("&x\n/\n")
    assert any("run.nml" in p for p in I.check(case, tmp_path, ["case_template"]))   # fails if blind


def test_case_template_lists_every_file_and_skips_directives(tmp_path):
    case = _runs(tmp_path, {"submit.sh": LAUNCHER, "run.nml": "! Base namelist.\n&x\n/\n",
                            "NOTES.md": "# Annotated reference\n\nbody\n", "plain.nml": "&x\n/\n"})
    I.write(case, tmp_path, ["case_template"])
    text = (case / "case_template" / "README.md").read_text()
    assert "| `submit.sh` | Packed runner, many cases per node. |" in text     # not the #SBATCH line
    assert "| `run.nml` | Base namelist. |" in text
    assert "| `NOTES.md` | Annotated reference |" in text
    assert "| `plain.nml` | -- |" in text                                     # shown, not required
    assert I.check(case, tmp_path, ["case_template"]) == []
    assert text.index("## Run-file index") < text.index("## Skills") or \
        text.index("## Run-file index") < text.index("## Traps")                # near the top


def test_tier_scoping_leaves_the_other_folder_alone(tmp_path):
    case = _runs(tmp_path, {"submit.sh": LAUNCHER})
    (case / "scripts").mkdir()
    (case / "scripts" / "README.md").write_text("# scripts\n")
    (case / "scripts" / "plot_a.py").write_text(PY)
    I.write(case, tmp_path, ["case_template"])
    assert (case / "scripts" / "README.md").read_text() == "# scripts\n"
