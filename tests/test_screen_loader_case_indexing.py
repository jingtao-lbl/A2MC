"""The design matrix is indexed by case-1, not by case.

This is the 2026-08-23 defect: `xm = np.loadtxt(design_matrix_txt)[case]` was off by one for every
case. It survived because a Saltelli design's adjacent rows agree in most columns, so the wrong
lookup returned the right value most of the time. The test therefore pins the mapping directly
rather than sampling a case and hoping it is one of the ones that differ.
"""
import importlib.util
import pathlib

import numpy as np
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCR = REPO / "use_cases/EcoSIM_BioCON/scripts/screen_params_vs_targets.py"


def _load():
    spec = importlib.util.spec_from_file_location("scr", SCR)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _fixture(tmp_path, n_rows=6, n_cols=3):
    """A design matrix whose every row is distinguishable, so an off-by-one CANNOT hide."""
    X = np.arange(n_rows * n_cols, dtype=float).reshape(n_rows, n_cols)
    mx = tmp_path / "design.txt"
    np.savetxt(mx, X)
    y = tmp_path / "y.csv"
    y.write_text("case,plant_C\n" + "".join(f"{c},1.0\n" for c in (0, 1, 2, 5)))
    pl = tmp_path / "params.csv"
    pl.write_text("name,pft,units,surface,group,description,organ,element,default,lower_bound,upper_bound,bound_source\n"
                  + "".join(f"P{i},1,-,primary,g,d,-,-,0,0,100,s\n" for i in range(n_cols)))
    return y, mx, pl, X


def test_case_N_maps_to_row_N_minus_1(tmp_path):
    y, mx, pl, X = _fixture(tmp_path)
    scr = _load()
    case, _V, xm, _labels, _surface = scr.load_round(y, mx, pl, ["plant_C"])
    for i, c in enumerate(case):
        if c == 0:
            continue
        np.testing.assert_array_equal(
            xm[i], X[c - 1], err_msg=f"case {c} must map to design-matrix row {c - 1}")


def test_case_zero_has_no_design_row(tmp_path):
    """Case 0 is the unperturbed baseline. Returning a neighbour's parameters for it would make the
    baseline look like a sampled member, which is the contamination the alive mask exists to stop."""
    y, mx, pl, _X = _fixture(tmp_path)
    scr = _load()
    case, _V, xm, _labels, _surface = scr.load_round(y, mx, pl, ["plant_C"])
    z = np.where(case == 0)[0][0]
    assert np.isnan(xm[z]).all(), "case 0 must not borrow a design row"


def test_off_by_one_is_detectable_at_all(tmp_path):
    """Guard the guard: if every row were identical the two tests above would pass under the bug."""
    _y, _mx, _pl, X = _fixture(tmp_path)
    assert not np.array_equal(X[1], X[2]), "fixture rows must differ or the test proves nothing"
