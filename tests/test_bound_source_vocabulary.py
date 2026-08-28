"""Every rule of `tools/check_bound_source.py` fires, and the conforming baseline is clean.

Written failure-first (`feedback_a_check_that_cannot_fail`): each test names the mutation that
should be caught. Two of them are REGRESSIONS against errors made while designing this checker:

  * `test_all_five_prefixes_pass` -- the plan and `phase0-design` both listed THREE prefixes while
    the canonical template and `param_spec.py` define FIVE. A checker built from the plan would
    have ERRORED on every correct `measured:` and `prior_round:` row.
  * `test_mineral_axis_list_is_readable` -- the obvious implementation binds to
    `load_param_spec`, which coerces the grouping axis to an int and therefore RAISES on PFLOTRAN's
    live list and on every `parameter_list_template.csv`. That checker would have silently skipped
    the models this adapter kit exists for.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.param_spec import BOUND_SOURCE_PREFIXES  # noqa: E402

CHECKER = ROOT / "tools" / "check_bound_source.py"
HEADER = "name,pft,category,description,units,nc_dim,default,lower_bound,upper_bound,bound_source\n"


def run(*paths):
    """Return (exit_code, combined_output)."""
    r = subprocess.run([sys.executable, str(CHECKER), *[str(p) for p in paths]],
                       capture_output=True, text=True, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def write(tmp_path, rows, header=HEADER, preamble=""):
    p = tmp_path / "param_list.csv"
    p.write_text(preamble + header + "".join(rows))
    return p


def row(name, bound_source, default="1.0", lo="0.5", hi="1.5"):
    return f"{name},1,cat,desc,unit,npfts,{default},{lo},{hi},{bound_source}\n"


# ---------------------------------------------------------------- baseline

def test_all_five_prefixes_pass(tmp_path):
    """REGRESSION: all FIVE canonical prefixes are accepted, not the three the plan named."""
    rows = [
        row("A", "measured: BioCON ring means +/- 1SD, 2019-2023"),
        row("B", "literature: Amthor 2000 doi:10.1006/anbo.2000.1175"),
        row("C", "database: FRED root N:C; Iversen 2017 doi:10.1111/nph.14486"),
        row("D", "prior_round: R2 living regime narrowed the upper bound"),
        row("E", "provisional: default +/-50% -- refine before the next round"),
    ]
    code, out = run(write(tmp_path, rows))
    assert code == 0, out
    assert "✔" in out
    assert len(BOUND_SOURCE_PREFIXES) == 5


# ---------------------------------------------------------------- B1..B6

def test_b1_non_vocabulary_prefix_errors(tmp_path):
    code, out = run(write(tmp_path, [row("A", "R2 living-regime (base +/-50%)")]))
    assert code == 2, out
    assert "do not start with one of" in out


def test_b2_blank_cell_errors(tmp_path):
    """A blank reads as 'not recorded', indistinguishable from a published range."""
    code, out = run(write(tmp_path, [row("A", "")]))
    assert code == 2, out
    assert "blank" in out.lower()


def test_b3_missing_column_warns_but_does_not_error(tmp_path):
    """WARN not ERROR: the column is documented OPTIONAL and three live lists predate it."""
    h = "name,pft,lower_bound,upper_bound,default,description\n"
    code, out = run(write(tmp_path, ["A,1,0.5,1.5,1.0,desc\n"], header=h))
    assert code == 1, out
    assert "no `bound_source` column" in out


def test_b4_literature_without_doi_warns(tmp_path):
    code, out = run(write(tmp_path, [row("A", "literature: growth yield is about 0.8 in C4 grasses")]))
    assert code == 1, out
    assert "no DOI or URL" in out


def test_b4_literature_with_doi_is_clean(tmp_path):
    code, out = run(write(tmp_path, [row("A", "literature: Amthor 2000 doi:10.1006/anbo.2000.1175")]))
    assert code == 0, out


def test_b5_carried_provisional_debt_warns(tmp_path):
    """A provisional bound byte-identical to round N-1's was CARRIED, not paid."""
    same = "provisional: default +/-50% -- refine after Phase-1 mu*"
    (tmp_path / "list_r02.csv").write_text(HEADER + row("A", same))
    p3 = tmp_path / "list_r03.csv"
    p3.write_text(HEADER + row("A", same))
    code, out = run(p3)
    assert code == 1, out
    assert "CARRIED, not paid" in out


def test_b5_refined_provisional_is_clean(tmp_path):
    (tmp_path / "list_r02.csv").write_text(HEADER + row("A", "provisional: default +/-50%"))
    p3 = tmp_path / "list_r03.csv"
    p3.write_text(HEADER + row("A", "prior_round: R2 narrowed this on the living regime"))
    code, out = run(p3)
    assert code == 0, out


def test_b6_empty_selection_is_an_error_not_a_pass():
    """Anti-silent-pass: 'nothing matched' must never report success."""
    r = subprocess.run([sys.executable, str(CHECKER), str(ROOT / "tools" / "does_not_exist.csv")],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 2


# ---------------------------------------------------------------- multi-model scope

def test_mineral_axis_list_is_readable(tmp_path):
    """REGRESSION: PFLOTRAN's axis is a MINERAL NAME. `load_param_spec` raises on it; this must not.

    A checker bound to the loader would skip PFLOTRAN and every parameter_list_template.csv, and
    report success -- passing by not looking, on the models the adapter kit exists for.
    """
    from tools.param_spec import load_param_spec
    rows = ["RATE_CONSTANT,Calcite,kinetics,d,log10,,-8.8,-9.8,-7.8,"
            "literature: Palandri 2004 doi:10.3133/ofr20041068\n"]
    p = write(tmp_path, rows)
    with pytest.raises(ValueError):          # the loader cannot read it ...
        load_param_spec(p)
    code, out = run(p)                       # ... but the checker can
    assert code == 0, out


def test_region_axis_list_is_readable(tmp_path):
    """THIRD axis type, and the one with no case yet: ATS groups by REGION
    (`models/ats/spec.py` grouping_axis="region"), carried in `pft` as the documented
    single-axis stopgap — same shape as PFLOTRAN's minerals, different vocabulary.

    Pinned because ATS ships a complete adapter and has NO use case, so nothing else in the
    repo exercises this shape. A checker "generic across models" that had only ever been run
    against the two models with cases would be generic by assumption.
    """
    from tools.param_spec import load_param_spec
    rows = ["permeability,upland,hydrology,d,m2,,1.0e-12,5.0e-13,2.0e-12,"
            "provisional: seed; default x0.5 to x2\n"]
    h = "name,pft,category,description,units,nc_dim,default,lower_bound,upper_bound,bound_source\n"
    p = write(tmp_path, rows, header=h)
    with pytest.raises(ValueError):          # the loader cannot read a region axis ...
        load_param_spec(p)
    code, out = run(p)                       # ... the checker can
    assert code == 0, out


def test_every_live_grouping_axis_is_covered(tmp_path):
    """The three axis types onboarded today, in one place: integer PFT (EcoSIM/FATES), mineral
    name (PFLOTRAN), region name (ATS). If a fourth model lands with a new axis, this is where
    the coverage claim should be extended rather than assumed."""
    h = "name,pft,category,description,units,nc_dim,default,lower_bound,upper_bound,bound_source\n"
    for axis in ("1", "Calcite", "upland", "", "-"):
        rows = [f"P,{axis},cat,d,u,,1.0,0.5,1.5,provisional: seed; default x0.5 to x2\n"]
        code, out = run(write(tmp_path, rows, header=h))
        assert code == 0, f"axis {axis!r} not handled:\n{out}"


def test_fates_legacy_dialect_is_recognized(tmp_path):
    """The FATES lists use `fates_name`, not `name`. Not a parameter list is a different finding."""
    h = "fates_name,pft,organ,lower,upper,default_api43,description\n"
    code, out = run(write(tmp_path, ["fates_leaf_slatop,1,1,0.005,0.03,0.012,SLA\n"], header=h))
    assert code == 1, out
    assert "no `bound_source` column" in out
    assert "not a parameter list" not in out


def test_comments_after_the_header_are_not_counted_as_rows(tmp_path):
    """PFLOTRAN's live list has 145 comment lines around 17 rows; slicing at the header alone
    reported 115. A count nobody can trust is how a checker's output stops being read."""
    h = "name,pft,lower_bound,upper_bound,default,description\n"
    rows = ["A,1,0.5,1.5,1.0,d\n", "# an interleaved note\n", "B,1,0.5,1.5,1.0,d\n"]
    code, out = run(write(tmp_path, rows, header=h))
    assert "(2 rows)" in out, out


def test_grandfather_marker_downgrades_error_to_warning(tmp_path):
    """In-file, so it survives a rename and is visible to whoever edits the list."""
    bad = [row("A", "R2 living-regime, no prefix")]
    code, _ = run(write(tmp_path, bad))
    assert code == 2
    code, out = run(write(tmp_path, bad, preamble="# a2mc: bound-source-grandfathered\n"))
    assert code == 1, out
    assert "GRANDFATHERED" in out


# ---------------------------------------------------------------- live tree

def test_every_shipped_template_conforms():
    """The templates are the vocabulary's own worked examples -- they must never be the offender."""
    templates = sorted(ROOT.glob("use_cases/*/parameters/parameter_list_template.csv"))
    assert templates, "no parameter_list_template.csv found -- the glob or the layout changed"
    code, out = run(*templates)
    assert code == 0, out
