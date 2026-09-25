"""`create_use_case` — the scaffold contract.

Until 2026-08-03 this was an inline bash block in the `onboard-case` skill. It produced an
EMPTY `config/` and reported success on all three models, because `${MODEL,,}` is bash 4
syntax and macOS ships bash 3.2 (dev log `20260802g`). A recipe in prose cannot be tested,
which is the whole reason it became a script. These lock what it must do:

  * the directory is `<Prefix>_<Case>`, the prefix read from the adapter's own ModelSpec
  * an existing case is NEVER overwritten (it holds round records, logs and results)
  * a model with no case template routes to `onboard-model` instead of scaffolding junk
  * exactly this model's two config files survive; the other models' templates do not
  * a case literally named "template" still works -- the first version deleted its own
    output, because the cleanup globbed `*_template_*` after the rename
  * a failed scaffold leaves nothing behind
"""
import pathlib
import re

import pytest

from tools.create_use_case import (
    TEMPLATE_SUFFIXES, case_prefix, create, known_models, _read_prefix,
)

MODELS = ("fates", "ecosim", "pflotran")


@pytest.fixture
def fake_repo(tmp_path):
    """A repo skeleton with TEMPLATE carrying all three models' template pairs.

    fates and ecosim also get a README/targets seed (EXTRA_TEMPLATE_FILES); pflotran
    deliberately does NOT, so tests can exercise both the per-model-seed path and the
    soft-fallback-to-generic path in the same fixture.
    """
    (tmp_path / "a2mc_config.sh").write_text("# marker\n")
    tpl = tmp_path / "use_cases/TEMPLATE"
    cfg = tpl / "config"
    cfg.mkdir(parents=True)
    for m in MODELS:
        (cfg / f"{m}_template_config.sh").write_text(f"# {m} template\n")
        (cfg / f"{m}_template_calibration_rounds.yaml").write_text("rounds: {}\n")
    (tpl / "validation").mkdir()
    (tpl / "validation/targets.yaml").write_text("targets: {}  # generic\n")
    (tpl / "README.md").write_text("# generic template\n")
    for m in ("fates", "ecosim"):
        (tpl / f"{m}_template_readme.md").write_text(f"# {m} template readme\n")
        (tpl / f"validation/{m}_template_targets.yaml").write_text(f"targets: {{}}  # {m}\n")
    return tmp_path


# --- prefix resolution ------------------------------------------------------------

def test_prefix_comes_from_the_adapter_spec():
    """Not a hardcoded table: the prefix is the adapter's own display_name, so it cannot
    drift from the model's identity."""
    assert case_prefix("ecosim") == "EcoSIM"
    assert case_prefix("pflotran") == "PFLOTRAN"


def test_fates_prefix_is_declared_not_read():
    """FATES has no models/fates/ package -- it is A2MC's built-in default path.

    The prefix is **ELM-FATES**, not FATES (corrected 2026-08-26 with the template-folder rename):
    FATES runs under several host land models, the case tree pairs it with ELM throughout
    (`ELM-FATES_Kougarok`, `ELM-FATES_template`), and `models/base.py`'s own `display_name` docstring
    gives "ELM-FATES" as the canonical example. This assertion IS the contract -- it caught the
    rename, which is what it is for.
    """
    assert case_prefix("fates") == "ELM-FATES"
    assert _read_prefix("fates") == "ELM-FATES"


def test_unknown_model_names_the_known_ones():
    with pytest.raises(ValueError) as e:
        case_prefix("nosuchmodel")
    assert "onboard-model" in str(e.value) and "ecosim" in str(e.value)


def test_known_models_excludes_non_calibratable_modules():
    """models/surrogate/ has a spec.py but declares no ModelSpec; it is not a case host."""
    ks = known_models()
    assert {"fates", "ecosim", "pflotran"} <= set(ks)
    assert "surrogate" not in ks and "_template" not in ks


# --- the core scaffold ------------------------------------------------------------

@pytest.mark.parametrize("model,prefix", [("fates", "ELM-FATES"), ("ecosim", "EcoSIM"),
                                          ("pflotran", "PFLOTRAN")])
def test_creates_only_this_models_config(fake_repo, model, prefix):
    dest = create(model, "Toolik", root=fake_repo)
    assert dest.name == f"{prefix}_Toolik"
    names = sorted(p.name for p in (dest / "config").iterdir())
    assert names == ["calibration_rounds.yaml", f"{model}_toolik_config.sh"]
    # the other two models' templates are gone, not merely renamed
    assert not [p for p in (dest / "config").iterdir()
                if p.name.endswith(TEMPLATE_SUFFIXES)]


def test_case_named_template_does_not_delete_itself(fake_repo):
    """The regression that the first run found. `ecosim_template_config.sh` is BOTH the
    template name and the correct output name for a case called "template", so a cleanup
    that globs `*_template_*` after the rename removes the file it just produced."""
    dest = create("ecosim", "template", root=fake_repo)
    cfg = dest / "config/ecosim_template_config.sh"
    assert cfg.is_file(), "the scaffold deleted its own output"
    assert (dest / "config/calibration_rounds.yaml").is_file()
    assert not (dest / "config/fates_template_config.sh").exists()


def test_content_is_this_models_template(fake_repo):
    """Guards against the pair being crossed -- a PFLOTRAN case getting FATES's file."""
    dest = create("pflotran", "miniLEO", root=fake_repo)
    assert "pflotran template" in (dest / "config/pflotran_minileo_config.sh").read_text()


def test_non_config_content_is_carried_over(fake_repo):
    dest = create("ecosim", "Toolik", root=fake_repo)
    assert (dest / "validation/targets.yaml").is_file()


def test_readme_and_targets_get_this_models_seed(fake_repo):
    """A model with an authored seed (EXTRA_TEMPLATE_FILES) gets ITS OWN README/targets,
    not the generic FATES-flavored copy -- the gap 2 fix."""
    dest = create("ecosim", "Toolik", root=fake_repo)
    assert "ecosim template readme" in (dest / "README.md").read_text()
    assert "# ecosim" in (dest / "validation/targets.yaml").read_text()
    # the other model's seed is gone, not merely left alongside
    assert not (dest / "fates_template_readme.md").exists()
    assert not (dest / "validation/fates_template_targets.yaml").exists()
    assert not (dest / "ecosim_template_readme.md").exists()  # renamed, not left in place


def test_readme_and_targets_fall_back_to_generic_when_unseeded(fake_repo):
    """pflotran has no seed in this fixture -- soft-optional fallback to the generic
    TEMPLATE copy (mirrors calibration_rounds.yaml's existing optional behavior), not a
    hard refusal like a missing config.sh."""
    dest = create("pflotran", "miniLEO", root=fake_repo)
    assert (dest / "README.md").read_text() == "# generic template\n"
    assert (dest / "validation/targets.yaml").read_text() == "targets: {}  # generic\n"


def test_case_named_template_does_not_delete_readme_or_targets(fake_repo):
    """Same collision class as test_case_named_template_does_not_delete_itself: for a case
    literally named "template", ecosim's seed filename (`ecosim_template_readme.md`) is
    byte-identical to the string the swap renames it TO reaching for -- a naive
    `*_template_*` cleanup after the rename would delete the file it just produced."""
    dest = create("ecosim", "template", root=fake_repo)
    assert (dest / "README.md").is_file()
    assert "ecosim template readme" in (dest / "README.md").read_text()
    assert (dest / "validation/targets.yaml").is_file()


# --- refusals ---------------------------------------------------------------------

def test_never_overwrites_an_existing_case(fake_repo):
    """The PI's explicit constraint. An existing case is the longest-lived part of the
    work; there is deliberately no --force."""
    first = create("ecosim", "BioCON", root=fake_repo)
    (first / "config/ecosim_biocon_config.sh").write_text("# HAND-EDITED, must survive\n")
    (first / "memory").mkdir()
    (first / "memory/round_record.json").write_text("{}")

    with pytest.raises(SystemExit, match="already exists"):
        create("ecosim", "BioCON", root=fake_repo)

    assert "HAND-EDITED" in (first / "config/ecosim_biocon_config.sh").read_text()
    assert (first / "memory/round_record.json").is_file()


def test_missing_template_routes_to_onboard_model(fake_repo):
    """ATS is a registered adapter with no case template. The refusal must name the fix,
    not just report absence -- a missing template always means the model was never
    onboarded that far."""
    with pytest.raises(SystemExit, match="onboard-model"):
        create("ats", "OakHarbor", root=fake_repo)
    assert not (fake_repo / "use_cases/ATS_OakHarbor").exists()


@pytest.mark.parametrize("bad", ["bad name", "a/b", "../escape", ".hidden", ""])
def test_unsafe_case_names_refused(fake_repo, bad):
    with pytest.raises(SystemExit, match="usable directory component"):
        create("ecosim", bad, root=fake_repo)


def test_not_an_a2mc_clone(tmp_path):
    with pytest.raises(SystemExit, match="not an A2MC clone"):
        create("ecosim", "X", root=tmp_path)


def test_missing_seed_refused(fake_repo):
    with pytest.raises(SystemExit, match="does not exist"):
        create("ecosim", "X", seed="NoSuchSeed", root=fake_repo)


# --- dry run + seeding from a filled case -----------------------------------------

def test_dry_run_writes_nothing(fake_repo):
    create("ecosim", "Toolik", dry_run=True, root=fake_repo)
    assert not (fake_repo / "use_cases/EcoSIM_Toolik").exists()


def test_seed_from_a_filled_case_renames_its_config(fake_repo):
    """The Kougarok path: seed from a worked case, keep its values, rename to the new case."""
    src = create("fates", "Kougarok", root=fake_repo)
    (src / "config/fates_kougarok_config.sh").write_text("# 3-PFT arctic\n")

    dest = create("fates", "Toolik", seed=f"{case_prefix('fates')}_Kougarok", root=fake_repo)
    cfg = dest / "config/fates_toolik_config.sh"
    assert cfg.is_file() and "3-PFT arctic" in cfg.read_text()
    assert not (dest / "config/fates_kougarok_config.sh").exists()


def test_a_case_seed_does_not_carry_its_history_or_state(fake_repo):
    """A seeded case must not start life 'running': the seed's workflow state, logs, results,
    reports, knowledge and plan belong to the seed site (audit 20260923b, persona P4)."""
    src = create("fates", "Kougarok", root=fake_repo)
    (src / "config/fates_kougarok_config.sh").write_text("# 3-PFT arctic\n")
    (src / "memory/logs").mkdir(parents=True)
    (src / "memory/workflow_state_offline_r01.json").write_text("{}")
    (src / "memory/logs/r1.md").write_text("# a round of Kougarok\n")
    (src / "reports/r1").mkdir(parents=True)
    (src / "reports/r1/summary.md").write_text("# Kougarok R1\n")
    (src / "research_plan.md").write_text("# Kougarok's plan\n")

    dest = create("fates", "Toolik", seed=f"{case_prefix('fates')}_Kougarok", root=fake_repo)
    assert "3-PFT arctic" in (dest / "config/fates_toolik_config.sh").read_text()  # values kept
    assert not (dest / "memory/workflow_state_offline_r01.json").exists()
    assert not (dest / "memory/logs/r1.md").exists()
    assert not (dest / "reports/r1").exists()
    assert not (dest / "research_plan.md").exists()


def test_failed_scaffold_leaves_nothing_behind(fake_repo):
    """A half-built case is worse than none: it looks scaffolded and is not."""
    (fake_repo / "use_cases/TEMPLATE/config/ecosim_template_config.sh").unlink()
    with pytest.raises(SystemExit):
        create("ecosim", "Toolik", root=fake_repo)
    assert not (fake_repo / "use_cases/EcoSIM_Toolik").exists()


# --- the parameter-list template the scaffold copies -------------------------------

def test_template_param_list_actually_parses():
    """It shipped UNPARSEABLE until 2026-08-03 while naming, in its own header, the loader that
    could not read it. Two separate causes, both silent:

      * bound columns named `lower`/`upper`. _find_header_row matches the bare form on a
        WHITESPACE split, so in a comma-separated header they are one token and never match.
      * a preamble comment line containing BOTH suffixed bound names, which is then selected
        as the header row instead of the real one.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.create_adapter_parameter_sample import parse_pft_param_list

    root = Path(__file__).resolve().parent.parent
    names, lower, upper = parse_pft_param_list(
        root / "use_cases/TEMPLATE/parameters/parameter_list_template.csv")

    assert len(names) >= 3, "the template must carry usable example rows"
    assert len(set(names)) == len(names), "duplicate canonical ids"
    assert all(l < u for l, u in zip(lower, upper))
    # the schema must demonstrate more than one grouping-axis shape
    assert any("_" in n and n.split("_")[-1].isdigit() for n in names), "no integer-group example"
    assert any(n.endswith(("Calcite", "Glass_FB")) for n in names), "no named-group example"


def _template_text():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    return (root / "use_cases/TEMPLATE/parameters/parameter_list_template.csv").read_text()


def test_template_param_list_is_canonical_not_fates_legacy():
    """The canonical dialect is EcoSIM's. A new case must not be seeded with the FATES legacy
    header, which would propagate a second dialect to every model onboarded from here."""
    cols = next(l for l in _template_text().splitlines() if l.startswith("name,")).split(",")
    assert cols[0] == "name" and "fates_name" not in cols
    assert "lower_bound" in cols and "upper_bound" in cols
    assert "lower" not in cols and "upper" not in cols
    assert "bound_source" in cols, "bounds provenance column is required by the canonical form"


def test_template_ships_both_basic_axes():
    """PI decision 2026-08-02: `pft` and `organ` are the BASIC axes and BOTH ship in the default
    template, because the axis set is meant to be EXTENSIBLE -- a model adds `mineral`, a
    microbial guild, a chemical species. A first pass dropped `organ` on the grounds that the
    adapter loader ignores it, which confused a LOADER limitation with the SCHEMA."""
    cols = next(l for l in _template_text().splitlines() if l.startswith("name,")).split(",")
    assert "pft" in cols and "organ" in cols
    text = _template_text()
    assert "EXTENSIBLE" in text, "the extensibility rule must be stated, not implied"
    for planned in ("mineral", "microbial_guild", "species"):
        assert planned in text, f"the axis rule must name {planned} as an addable axis"


def test_bound_source_vocabulary_is_documented_and_used():
    """A bound with no stated provenance is indistinguishable from a published range. The
    vocabulary must be documented AND demonstrated in the example rows."""
    text = _template_text()
    for token in ("measured:", "literature:", "database:", "prior_round:", "provisional:"):
        assert token in text, f"bound_source vocabulary is missing {token}"
    assert "TRY" in text and "FRED" in text, "name the trait databases explicitly"

    data = [l for l in text.splitlines() if l and not l.startswith("#") and not l.startswith("name,")]
    assert data, "no example rows"
    for row in data:
        src = row.split(",")[-1]
        assert src.startswith(("measured:", "literature:", "database:", "prior_round:",
                               "provisional:")), f"example row has an off-vocabulary source: {src[:60]}"
    assert any("doi:" in r for r in data), "a literature/database example must show a DOI"


def test_template_rows_have_no_stray_commas():
    """There is no quoting step: one comma in a free-text cell shifts every later column. This
    fired on the first rewrite -- a bound_source read `default +/-50%, refine ...`."""
    header = next(l for l in _template_text().splitlines() if l.startswith("name,"))
    n = len(header.split(","))
    for row in [l for l in _template_text().splitlines()
                if l and not l.startswith("#") and not l.startswith("name,")]:
        assert len(row.split(",")) == n, f"field count {len(row.split(','))} != {n}: {row[:70]}"


# --- the committed *_template demo cases stay in sync with TEMPLATE ----------------

def _fake_root_with(model_template: pathlib.Path, tmp: pathlib.Path) -> pathlib.Path:
    """A minimal fake clone carrying one authored per-model template dir."""
    import shutil
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "a2mc_config.sh").write_text("# marker\n")
    shutil.copytree(model_template, tmp / "use_cases" / model_template.name,
                    ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"))
    return tmp


def test_default_seed_is_the_models_own_template_dir():
    """ARCHITECTURE B (PI, 2026-08-17): `<Prefix>_template/` is AUTHORED SOURCE and is the
    default seed. Previously it was a generated snapshot of `TEMPLATE/` and a drift test
    enforced that, which is exactly why a per-model file could not live in one -- the next
    regeneration deleted it. This replaces that drift test.
    """
    from tools.create_use_case import case_prefix, resolve_seed
    root = pathlib.Path(__file__).resolve().parent.parent
    for model in ("fates", "ecosim", "pflotran"):
        own = root / "use_cases" / f"{case_prefix(model)}_template"
        expect = own.name if own.is_dir() else "TEMPLATE"
        assert resolve_seed(root, model, None) == expect, model
        # an explicit --seed still wins, or `--seed Kougarok` would silently stop working
        assert resolve_seed(root, model, "Kougarok") == "Kougarok"


def test_authored_template_dirs_actually_scaffold(tmp_path):
    """Each authored per-model template must produce a real case. Under B nothing regenerates
    these dirs, so a broken one is only discovered by someone onboarding a case."""
    from tools.create_use_case import case_prefix, create
    root = pathlib.Path(__file__).resolve().parent.parent
    checked = 0
    for model in ("fates", "ecosim", "pflotran"):
        own = root / "use_cases" / f"{case_prefix(model)}_template"
        if not own.is_dir():
            continue
        fake = _fake_root_with(own, tmp_path / model)
        dest = create(model, "probe", root=fake)
        cfg = dest / "config" / f"{model}_probe_config.sh"
        assert cfg.is_file(), f"{model}: scaffold produced no {cfg.name}"
        leftover = sorted(p.name for p in (dest / "config").glob("*_template_config.sh"))
        assert not leftover, f"{model}: template config left behind: {leftover}"
        checked += 1
    assert checked, "no authored *_template dir found -- did they get deleted?"


def test_ecosim_template_ships_the_namelist_its_config_points_at():
    """F1, the audit that motivated B (`20260816a`): every scaffolded EcoSIM case was born
    pointing at `case_template/run.nml`, which existed nowhere in the template tree. It failed
    late, inside create_case(), long after the author believed setup had succeeded.
    """
    root = pathlib.Path(__file__).resolve().parent.parent
    tpl = root / "use_cases/EcoSIM_template"
    if not tpl.is_dir():
        pytest.skip("EcoSIM_template not present")
    cfg = (tpl / "config/ecosim_template_config.sh").read_text()
    m = re.search(r'A2MC_ECOSIM_BASE_NAMELIST="\$\{A2MC_USE_CASE_DIR\}/(.+?)"', cfg)
    assert m, "config declares no A2MC_ECOSIM_BASE_NAMELIST"
    assert (tpl / m.group(1)).is_file(), (
        f"config points at {m.group(1)} but the template does not ship it")


def test_ecosim_template_namelist_fits_the_read_buffer():
    """EcoSIM reads the namelist into a FIXED 4096-byte buffer and abort()s when the read FILLS
    it -- too LONG fails, not too short (`fileUtil.F90`; 20260810a). The template must leave
    room, because real absolute paths replace short placeholders and each costs ~100 bytes.
    """
    root = pathlib.Path(__file__).resolve().parent.parent
    nml = root / "use_cases/EcoSIM_template/case_template/run.nml"
    if not nml.is_file():
        pytest.skip("no template namelist")
    size = len(nml.read_bytes())
    assert size < 4096, f"template namelist is already {size} bytes"
    # 6 substitutable path placeholders, each growing to a ~115-byte absolute CFS path
    assert size + 6 * 100 < 4096, (
        f"{size} bytes leaves under 600 bytes for real paths; trim comments")


# ---------------------------------------------------------------- the REAL repo ----------------
# Everything above builds a FAKE repo whose directory names the fixture chooses -- right for testing
# the scaffolder's logic, and structurally BLIND to the tree actually shipping. That blindness had a
# cost: when `use_cases/FATES_template/` was renamed to `use_cases/ELM-FATES_template/` on
# 2026-08-26, `BUILTIN_PREFIXES` still said "FATES", so `case_prefix("fates")` resolved to a folder
# that no longer existed and `create_use_case.py --model fates` could not find its own seed. Every
# test above passed.
#
# These two read the REAL repo, so renaming a shipped template folder cannot pass unnoticed again.


REAL_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_every_known_model_resolves_to_a_template_folder_that_EXISTS():
    """The bug the fixtures could not see: prefix -> a directory nobody moved."""
    models = known_models()
    assert models, "known_models() returned nothing -- this test would then assert nothing"
    missing = []
    for m in models:
        d = REAL_ROOT / "use_cases" / (case_prefix(m) + "_template")
        if not d.is_dir():
            missing.append(m + " -> " + str(d.relative_to(REAL_ROOT)))
    assert not missing, (
        "case_prefix() names a template folder that does not exist: " + "; ".join(missing) +
        " -- a template folder was renamed without updating BUILTIN_PREFIXES or that model's "
        "ModelSpec.display_name")


def test_the_shared_template_config_is_keyed_on_the_MODEL_KEY_not_the_folder_prefix():
    """The companion half, and the reason the file is NOT renamed to match its folder.

    `create_use_case.py` reads `use_cases/TEMPLATE/config/<model>_template_config.sh`, keyed on the
    MODEL KEY. So `fates_template_config.sh` living under a folder named `ELM-FATES_template` is
    deliberate: folder = display prefix, file = model key. Renaming the file to match the folder
    breaks this lookup unless the derivation changes too.
    """
    models = known_models()
    assert models
    shared = REAL_ROOT / "use_cases/TEMPLATE/config"
    missing = [m for m in models if not (shared / (m + "_template_config.sh")).is_file()]
    # ATS has no entry in the shared dir yet -- it ships its own authored template folder only.
    assert set(missing) <= {"ats"}, "missing shared template config for: " + str(missing)


def test_list_reports_the_seed_that_create_would_ACTUALLY_use():
    """`--list`'s template column must answer the question its header implies.

    Before 2026-08-26 it asked only whether the SHARED `TEMPLATE/config/<model>_template_config.sh`
    existed, so ATS -- which scaffolds perfectly from its own authored `ATS_template/` -- was
    reported as "NO -- run onboard-model". A column that answers a narrower question than it appears
    to is worse than no column, and this one sent a reader to a skill they did not need.
    """
    import subprocess, sys as _s
    from tools.create_use_case import resolve_seed, known_models, repo_root
    root = repo_root()
    r = subprocess.run([_s.executable, "tools/create_use_case.py", "--list"],
                       cwd=REAL_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rows = {l.split()[0]: l for l in r.stdout.splitlines()[1:] if l.strip()}
    assert rows, "--list printed no models; this test would then assert nothing"
    for m in known_models():
        seed = resolve_seed(root, m, None)
        exists = (root / "use_cases" / seed).is_dir()
        row = rows[m]
        if exists:
            assert "yes" in row and seed in row, f"{m}: --list says {row!r} but would seed from {seed}"
        else:
            assert "NO" in row, f"{m}: --list claims a template but {seed} does not exist"
