"""The optional `surface` column: documentation that is CHECKED, never a second source of truth.

A reader of a param list cannot otherwise tell which parameter FILE a row is written to, because
routing is derived by probing each base file's variables. The column closes that readability gap.
It must not become authoritative: if the CSV and the files disagree, either the list is stale or
the base file is not the one it was written against, and both are stop-the-run conditions.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.create_adapter_parameter_sample import (  # noqa: E402
    declared_surfaces, route_surfaces,
)

IDS = ["A_1", "B", "C"]
PRIMARY = {"A", "B"}
TERTIARY = {"C"}


def _write(tmp_path, rows, header="name,pft,surface,lower_bound,upper_bound"):
    p = tmp_path / "list.csv"
    p.write_text("# a comment line the parser must skip\n" + header + "\n" + "\n".join(rows) + "\n")
    return p


def test_honest_column_passes():
    r = route_surfaces(IDS, PRIMARY, TERTIARY, True,
                       declared={"A_1": "primary", "B": "primary", "C": "tertiary"})
    assert r == {"A_1": "primary", "B": "primary", "C": "tertiary"}


def test_a_wrong_surface_raises_rather_than_being_silently_corrected():
    """The probe wins, but silently. Correcting without complaint would hide a stale list."""
    with pytest.raises(ValueError, match="disagrees with the actual base files"):
        route_surfaces(IDS, PRIMARY, TERTIARY, True,
                       declared={"A_1": "primary", "B": "primary", "C": "primary"})


def test_a_declared_row_that_is_not_sampled_raises():
    """A row declared but absent from the sample means the list and the run disagree about what
    is being calibrated, which is worth stopping for."""
    with pytest.raises(ValueError, match="not in the sampled set"):
        route_surfaces(IDS, PRIMARY, TERTIARY, True, declared={"A_1": "primary", "GHOST": "primary"})


def test_no_declaration_is_unchanged_behaviour():
    """Lists without the column (PFLOTRAN's, Lusignan's, R1/R2's) must keep working untouched."""
    assert route_surfaces(IDS, PRIMARY, TERTIARY, True) == \
           route_surfaces(IDS, PRIMARY, TERTIARY, True, declared={})


def test_declared_surfaces_returns_empty_when_the_column_is_absent(tmp_path):
    p = _write(tmp_path, ["A,1,0.1,0.2"], header="name,pft,lower_bound,upper_bound")
    assert declared_surfaces(p) == {}


def test_declared_surfaces_skips_comments_and_builds_canonical_ids(tmp_path):
    p = _write(tmp_path, ["A,1,primary,0.1,0.2", "B,-,tertiary,0.1,0.2"])
    assert declared_surfaces(p) == {"A_1": "primary", "B": "tertiary"}


def test_the_live_r3_list_declares_surfaces_that_match_its_own_rows():
    """The real list, checked for internal consistency without needing the NetCDF files present."""
    live = REPO / "use_cases/EcoSIM_BioCON/parameters/ecosim_biocon_param_list_r03.csv"
    if not live.is_file():
        pytest.skip("R3 list absent")
    d = declared_surfaces(live)
    assert len(d) == 28, f"expected 28 declared rows, got {len(d)}"
    assert set(d.values()) == {"primary", "tertiary"}, sorted(set(d.values()))
    # the microbial parameters are the tertiary surface; nothing else is
    tert = {k.rsplit("_", 1)[0] if k[-1].isdigit() else k for k, v in d.items() if v == "tertiary"}
    assert tert == {"RCCZ", "VMXO", "RMOM", "GO2X", "SPORC", "SPOMC", "DCKML"}, sorted(tert)


# ---------------------------------------------------------------------------
# The template's commented example rows must not parse as live parameters
# ---------------------------------------------------------------------------
def test_template_commented_examples_do_not_become_parameters():
    """`parse_pft_param_list` calls pd.read_csv WITHOUT comment='#', so every line after the
    header is data. The template's illustrative rows escape only because their bound columns hold
    `...` placeholders rather than numbers.

    Caught live on 2026-08-18: an example row added with REAL bounds parsed as a parameter named
    `# SPORC`, which a user copying the template would have sampled. Placeholders are load-bearing,
    not stylistic.
    """
    from scripts.create_adapter_parameter_sample import parse_pft_param_list
    tpl = REPO / "use_cases/EcoSIM_template/parameters/parameter_list_template.csv"
    if not tpl.is_file():
        pytest.skip("template absent")
    ids, _, _ = parse_pft_param_list(tpl)
    phantom = [i for i in ids if i.lstrip().startswith("#")]
    assert not phantom, (
        f"commented example rows parsed as live parameters: {phantom}. Put `...` in their bound "
        f"columns so they are dropped, as the other examples do.")


def test_template_declares_the_microbial_axis_alongside_the_mineral_one():
    """Both live uses of the `pft` stopgap must be visible, or the next model repeats the mistake
    of overloading `pft` without declaring what it overloaded it with."""
    tpl = REPO / "use_cases/EcoSIM_template/parameters/parameter_list_template.csv"
    if not tpl.is_file():
        pytest.skip("template absent")
    txt = tpl.read_text()
    assert "biomass_component" in txt, "the necrobiomass axis is not declared in the axis table"
    assert "do NOT overload `pft`" in txt, "the rule this column exists to satisfy went missing"


def test_row_count_and_distinct_name_count_are_not_confused():
    """P for a Sobol design is the number of independently-sampled COLUMNS = rows, not the number
    of distinct parameter NAMES. The two differ whenever a parameter spans an axis.

    Pinned because they were confused in a committed report, changelog and state entry on
    2026-08-18: the list was described as "27 distinct parameters" (it is 26) and costed at P=27
    (it is 28), which understated the ensemble by 512 cases. The template's invariant is explicit:
    one row = one independently-sampled parameter = one matrix column.
    """
    import csv
    from collections import Counter
    live = REPO / "use_cases/EcoSIM_BioCON/parameters/ecosim_biocon_param_list_r03.csv"
    if not live.is_file():
        pytest.skip("R3 list absent")
    rows = list(csv.DictReader([l for l in live.read_text().splitlines()
                                if l.strip() and not l.startswith("#")]))
    names = Counter(r["name"] for r in rows)
    assert len(rows) == 28, f"sampled columns (P) = {len(rows)}"
    assert len(names) == 26, f"distinct names = {len(names)}"
    assert {k: v for k, v in names.items() if v > 1} == {"SPORC": 2, "SPOMC": 2}

    header = live.read_text().split("\n", 3)
    blob = "\n".join(header[:3])
    assert "28 rows" in blob and "26 distinct" in blob, (
        f"the header must state BOTH counts and not conflate them:\n{blob}")
