"""
Golden test for the canonical param-list loader (docs/37, Stage 0b).

Locks the new `tools/param_spec.load_param_spec()` against the legacy
`tools/modify_fates_parameters.build_param_lookup()` on the shared rows of the
migrated Kougarok CSV, so the refactor stays behavior-preserving through Stages 1–2.
"""
import re
from pathlib import Path

import pytest

from tools.param_spec import load_param_spec

REPO = Path(__file__).resolve().parents[1]
# Resolve the api-43 param CSV by glob so a filename suffix change (e.g. _para171) does
# not break the test — it did on 2026-07-10 when the file was renamed.
_API43_CSVS = sorted(REPO.glob("use_cases/ELM-FATES_Kougarok/parameters/FATES_Parameter_List_api43*.csv"))
CSV = _API43_CSVS[0] if _API43_CSVS else REPO / "use_cases/ELM-FATES_Kougarok/parameters/FATES_Parameter_List_api43_para171.csv"
# Derive the expected row count from the CSV's own `paraNNN` suffix instead of hardcoding it.
# The count lives in the filename by convention (v2.202 de-hardcoding), so a list change
# (171 -> 168 on 2026-07-12, dropping the inactive eca_alpha_ptase rows) no longer strands
# these assertions — they now check loader-rows == filename-count, which is the real invariant.
N_PARAMS = int(re.search(r"para(\d+)", CSV.name).group(1))
TXT = REPO / "use_cases/ELM-FATES_Kougarok/parameters/FATES_Parameter_List_Full_162_Finalized.txt"

RETRANS = {"fates_cnp_turnover_nitr_retrans", "fates_cnp_turnover_phos_retrans"}
# names the api-43 migration renamed/split, so they intentionally differ from the legacy list
MIGRATED = {"fates_turnover_leaf_canopy", "fates_turnover_leaf_ustory"}
# api-43 seed-allocation reparameterization (dev_logs/20260710a): the legacy `fates_recruit_seed_alloc`
# rows were replaced by the virtual coords seed_repro_fraction/seed_alloc_fraction, and the previously
# fixed `fates_recruit_seed_dbh_repro_threshold` was added as a calibrated param — all intentional.
REPARAM_NEW = {"seed_repro_fraction", "seed_alloc_fraction", "fates_recruit_seed_dbh_repro_threshold"}
# `fates_cnp_eca_alpha_ptase` was dropped from the api-43 list in v2.202 (3 rows, PFTs 10/11/12):
# it is INACTIVE in api-43 ECA and hard-guarded to 0 in FatesCheckParams (the run crashes if it is
# nonzero), while it was active in api-31 — so the legacy list legitimately still carries it.
# See ana_logs/20260712a and memory `reference_fates_eca_ptase_disabled_api43`.
REPARAM_DROPPED = {"fates_recruit_seed_alloc", "fates_cnp_eca_alpha_ptase"}
# api-31 (12-PFT) -> api-43 (14-PFT) Kougarok PFT remap (arctic variants): evergreen 7->10, decid 9->11, graminoid 10->12
PFT_REMAP = {7: 10, 9: 11, 10: 12}


def test_csv_loads_and_counts():
    specs = load_param_spec(CSV)
    assert len(specs) == N_PARAMS
    assert len({s.canonical_id for s in specs}) == N_PARAMS  # ids unique
    # seed reparameterization landed: virtual coords present, native seed_alloc row gone
    names = {s.fates_name for s in specs}
    assert {"seed_repro_fraction", "seed_alloc_fraction"} <= names
    assert "fates_recruit_seed_alloc" not in names
    assert sum(1 for s in specs if s.is_virtual) == 6
    # stoich + retrans are organ-dimensioned; turnover_leaf is not
    organ_names = {s.fates_name for s in specs if s.is_organ}
    assert "fates_stoich_nitr" in organ_names
    assert "fates_cnp_turnover_nitr_retrans" in organ_names
    assert not any("turnover_leaf" in s.fates_name and s.is_organ for s in specs)


def test_canonical_id_scheme():
    specs = {s.canonical_id: s for s in load_param_spec(CSV)}
    # evergreen shrub is PFT#10 on api-43 (was #7)
    assert "fates_stoich_nitr#p10#o1" in specs          # leaf
    assert "fates_stoich_nitr#p10#o2" in specs          # fineroot
    assert "fates_cnp_turnover_nitr_retrans#p10#o1-2" in specs  # retrans broadcast
    assert specs["fates_cnp_turnover_nitr_retrans#p10#o1-2"].organ_slots() == [1, 2]
    # nfix1 was PFT#9 (deciduous shrub), remapped to arctic decid #11
    assert "fates_cnp_nfix1#p11" in specs
    assert specs["fates_cnp_nfix1#p11"].organ == []
    # graminoid is PFT#12 on api-43 (was #10)
    assert any(s.pft == 12 for s in specs.values())


@pytest.mark.skipif(not TXT.exists(), reason="legacy .txt not present")
def test_golden_vs_build_param_lookup():
    """The (fates_name, pft, organ) identity SET of the CSV reproduces build_param_lookup(old .txt),
    excluding the intentionally-migrated turnover_leaf names."""
    from tools.modify_fates_parameters import build_param_lookup
    lk = build_param_lookup(str(TXT))  # {shorthand: {fates_name, pft, organ}}

    def norm(fates, pft, organ):
        # retrans: legacy leaves organ implicit (None) → CSV makes it explicit [1,2]
        org = (1, 2) if fates in RETRANS else (() if organ is None else (organ,))
        return (fates, PFT_REMAP.get(pft, pft), org)   # api-31 -> api-43 PFT remap

    legacy = {norm(r["fates_name"], r["pft"], r["organ"])
              for r in lk.values()
              if r["fates_name"] != "fates_turnover_leaf" and r["fates_name"] not in REPARAM_DROPPED}
    csv = {(s.fates_name, s.pft, tuple(s.organ))
           for s in load_param_spec(CSV) if s.fates_name not in (MIGRATED | REPARAM_NEW)}

    assert csv == legacy, (
        f"\n  only in CSV:    {sorted(csv - legacy)}"
        f"\n  only in legacy: {sorted(legacy - csv)}")


# --- canonical-dialect acceptance (2026-08-03) -------------------------------------
#
# `load_param_spec` required {fates_name, pft, organ, lower, upper} and read line 0 as the
# header. So it accepted exactly ONE list in the repo -- FATES's -- and every canonical list
# (EcoSIM's, PFLOTRAN's, the template) failed. These lock both dialects loading, and lock the
# FATES path unchanged, since its live 168-param list must not be rewritten under a running round.

import pytest
from tools.param_spec import load_param_spec


CANON = ("name,pft,organ,lower_bound,upper_bound,default,description,bound_source\n"
         "CNLF,1,,0.02,0.2,0.1,leaf N:C,literature: Kerkhoff 2005 doi:10.1086/430237\n"
         "CNRT,1,,0.008,0.02,0.016,root N:C,database: FRED; Iversen 2017 doi:10.1111/nph.14486\n")
LEGACY = ("fates_name,pft,organ,lower,upper,default_api43,description\n"
          "fates_stoich_nitr,1,1,0.018,0.038,0.033,leaf N\n")


def _w(tmp_path, text, name="p.csv"):
    f = tmp_path / name
    f.write_text(text)
    return f


def test_canonical_dialect_loads(tmp_path):
    specs = load_param_spec(_w(tmp_path, CANON))
    assert [s.fates_name for s in specs] == ["CNLF", "CNRT"]
    assert [s.pft for s in specs] == [1, 1]
    assert specs[0].lower == 0.02 and specs[0].upper == 0.2


def test_legacy_dialect_still_loads(tmp_path):
    specs = load_param_spec(_w(tmp_path, LEGACY))
    assert specs[0].fates_name == "fates_stoich_nitr" and specs[0].organ == [1]


def test_bound_source_survives_the_loader(tmp_path):
    """Provenance that dies at the loader is provenance nobody downstream can act on."""
    specs = load_param_spec(_w(tmp_path, CANON))
    assert specs[0].bound_source.startswith("literature:")
    assert "doi:" in specs[1].bound_source
    # absent column -> empty, never an error
    assert load_param_spec(_w(tmp_path, LEGACY, "l.csv"))[0].bound_source == ""


def test_organ_column_is_optional(tmp_path):
    """organ is a FATES axis; a model without one omits the column. It was REQUIRED, so every
    canonical list failed on a column that does not apply to it."""
    text = CANON.replace("name,pft,organ,", "name,pft,").replace(",1,,", ",1,")
    specs = load_param_spec(_w(tmp_path, text))
    assert [s.organ for s in specs] == [[], []]
    assert specs[0].canonical_id == "CNLF#p1"


def test_comment_preamble_is_skipped(tmp_path):
    """The canonical template ships a long `#` preamble. DictReader takes line 0 as the header,
    so without skipping it every column reads as missing."""
    specs = load_param_spec(_w(tmp_path, "# schema notes\n#\n# more notes\n" + CANON))
    assert len(specs) == 2


@pytest.mark.parametrize("bad,field", [
    ("name,fates_name,pft,organ,lower_bound,upper_bound,default\nA,B,1,,0,1,0.5\n", "name"),
    ("name,pft,organ,lower,lower_bound,upper_bound,default\nA,1,,0,0,1,0.5\n", "lower"),
])
def test_both_spellings_present_is_ambiguous(tmp_path, bad, field):
    """A half-converted list is exactly when a silent preference picks the wrong column."""
    with pytest.raises(ValueError, match="Ambiguous"):
        load_param_spec(_w(tmp_path, bad))


def test_named_axis_error_is_actionable(tmp_path):
    """PFLOTRAN carries mineral NAMES in `pft` as the documented stopgap for the singular
    grouping axis. This loader's axis is integer-valued; the error must say where to go."""
    text = "name,pft,lower_bound,upper_bound,default\nRATE_CONSTANT,Calcite,-9.8,-7.8,-8.8\n"
    with pytest.raises(ValueError) as e:
        load_param_spec(_w(tmp_path, text))
    msg = str(e.value)
    assert "not an integer" in msg
    assert "parse_pft_param_list" in msg and "grouping_axis" in msg


def test_missing_columns_name_the_canonical_format(tmp_path):
    with pytest.raises(ValueError, match="Canonical format"):
        load_param_spec(_w(tmp_path, "name,pft\nA,1\n"))


# --- the real lists, end to end ----------------------------------------------------

def test_every_real_param_list_counts():
    """The regression that motivated this: count_param_list returned a silent 0 for EcoSIM's
    list -- exit 0, no warning -- straight into A2MC_N_PARAMS. FATES's counts are the
    no-regression anchor; its live list must not change under a running round."""
    from pathlib import Path
    from tools.count_param_list import count_params
    root = Path(__file__).resolve().parent.parent
    expected = {
        "use_cases/ELM-FATES_Kougarok/parameters/FATES_Parameter_List_api43_para168.csv": 168,
        "use_cases/ELM-FATES_Kougarok/parameters/FATES_Parameter_List_api43_para171.csv": 171,
        "use_cases/EcoSIM_BioCON/parameters/ecosim_biocon_param_list.csv": 40,
        "use_cases/PFLOTRAN_miniLEO/parameters/pflotran_minileo_param_list.csv": 16,
    }
    for rel, n in expected.items():
        assert count_params(root / rel) == n, rel
