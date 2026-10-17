"""tools/check_script_provenance.py: a new phase script names its template, or says there was none.

visibility: public

Each test builds a throwaway case and names the mistake it catches. The first is the positive control:
a phase script with no `Template:` line must be reported, or every pass below is vacuous.
"""
from tools.check_script_provenance import judge

TEMPLATE = '"""TEMPLATE: draw the thing."""\nprint(1)\n'


def _case(tmp_path, script_name, script_text, templates=("plot_a.py",), sub="20261020a_phase2_x"):
    case = tmp_path / "use_cases" / "Model_Case"
    (case / "scripts").mkdir(parents=True)
    for t in templates:
        (case / "scripts" / t).write_text(TEMPLATE)
    p = case / "memory" / "phase_results" / sub / script_name
    p.parent.mkdir(parents=True)
    p.write_text(script_text)
    return p


def test_no_line_is_reported(tmp_path):
    p = _case(tmp_path, "plot_new.py", '"""Draw a new thing."""\n')
    assert judge(p, tmp_path)                              # fails if a silent script passes


def test_named_existing_template_passes(tmp_path):
    p = _case(tmp_path, "plot_a.py", '"""Adapted.\n\nTemplate: scripts/plot_a.py\n"""\n')
    assert judge(p, tmp_path) is None


def test_case_relative_long_form_passes(tmp_path):
    p = _case(tmp_path, "plot_b.py", '"""Adapted.\n\nTemplate: use_cases/Model_Case/scripts/plot_a.py\n"""\n')
    assert judge(p, tmp_path) is None


def test_named_missing_template_is_reported(tmp_path):
    p = _case(tmp_path, "plot_b.py", '"""Adapted.\n\nTemplate: scripts/plot_zzz.py\n"""\n')
    assert judge(p, tmp_path)


def test_none_passes_when_no_same_named_template(tmp_path):
    p = _case(tmp_path, "plot_new.py", '"""New.\n\nTemplate: none (first use)\n"""\n')
    assert judge(p, tmp_path) is None


def test_none_beside_a_same_named_template_is_reported(tmp_path):
    p = _case(tmp_path, "plot_a.py", '"""New.\n\nTemplate: none (first use)\n"""\n')
    assert judge(p, tmp_path)


def test_unedited_copy_needs_no_line(tmp_path):
    p = _case(tmp_path, "plot_a.py", TEMPLATE)
    assert judge(p, tmp_path) is None


def test_shell_header_comment_counts(tmp_path):
    p = _case(tmp_path, "watch.sh", "#!/bin/bash\n# Watch it.\n# Template: none (first use)\n")
    assert judge(p, tmp_path) is None


def test_archived_run_files_are_skipped(tmp_path):
    p = _case(tmp_path, "submit.sh", "#!/bin/bash\nsrun x\n", sub="20261020a_phase0_x/run_tracking/submit_scripts")
    assert judge(p, tmp_path) is None


def _with_run_file(tmp_path, script_name, script_text):
    p = _case(tmp_path, script_name, script_text)
    ct = tmp_path / "use_cases" / "Model_Case" / "case_template"
    ct.mkdir()
    (ct / "submit_packed.sh").write_text("#!/bin/bash\n# Packed runner.\n")
    return p


def test_named_case_template_run_file_passes(tmp_path):
    p = _with_run_file(tmp_path, "launch.sh", "#!/bin/bash\n# Adapted.\n# Template: case_template/submit_packed.sh\n")
    assert judge(p, tmp_path) is None


def test_named_missing_run_file_is_reported(tmp_path):
    p = _with_run_file(tmp_path, "launch.sh", "#!/bin/bash\n# Template: case_template/nope.sh\n")
    assert judge(p, tmp_path)


def test_unedited_run_file_copy_needs_no_line(tmp_path):
    p = _with_run_file(tmp_path, "submit_packed.sh", "#!/bin/bash\n# Packed runner.\n")
    assert judge(p, tmp_path) is None


def test_none_beside_a_same_named_run_file_is_reported(tmp_path):
    p = _with_run_file(tmp_path, "submit_packed.sh", "#!/bin/bash\n# Changed.\n# Template: none (first use)\n")
    assert judge(p, tmp_path)
