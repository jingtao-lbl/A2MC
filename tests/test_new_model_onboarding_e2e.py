#!/usr/bin/env python
"""End-to-end "pretend onboarding a NEW model" test for the distilled adapter kit.

This is the distillation acceptance test (docs/38 §8A): it proves that a brand-new,
non-EcoSIM, non-FATES model flows through EVERY model-generic tool the adapter kit
ships — with NOTHING but its own ``models/<name>/`` adapter package (spec + backend)
plus a filled ``ModelSpec``. If a future genericization silently re-hardcodes EcoSIM
or FATES assumptions into one of these tools, this test goes red.

What it does:
  1. Scaffolds a minimal but WORKING mock adapter package ``models/mocktest/`` on disk
     (a real ``ModelBackend`` implementing the 8 abstract methods + a filled
     ``ModelSpec`` exercising the 7 distillation fields), with synthetic input/tape
     files — i.e. it stands up exactly what the ``onboard-model`` skill produces.
  2. Drives the generic surface against ``--model mocktest``:
       * ``tools/model_check_input_compat.py``  (exit 0 COMPATIBLE, exit 2 INCOMPATIBLE)
       * ``tools/model_evaluate_case.py``        (obs<->sim alignment, CLI + library)
       * ``tools.model_evaluate_case.reduce_target`` (flat group-select + time-reduce,
         incl. the negative-window edge that bit EcoSIM)
       * ``ModelBackend.select_group_series``    (default flat + a block-dim override)
       * ``scripts.model_generate_bounds._bounds`` (fraction [0,1] clamp + signed no-clamp)
  3. Tears the mock package + its bytecode down so the repo is left clean.

Run:  a2mc_env/bin/python -m pytest tests/test_new_model_onboarding_e2e.py -q

Author: Jing Tao with Claude
"""
from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
MODEL_DIR = REPO / "models" / "mocktest"
PYBIN = sys.executable


# --------------------------------------------------------------------------- #
# The mock adapter package — written verbatim to models/mocktest/ by the fixture.
# This IS the onboarding artifact: a filled spec + a working backend.
# --------------------------------------------------------------------------- #

_SPEC_PY = '''\
"""Mock ModelSpec for the adapter-kit onboarding e2e test (not a real model)."""
from __future__ import annotations
from ..base import ModelSpec

MOCKTEST_SPEC = ModelSpec(
    name="mocktest",
    display_name="MockTest",
    param_name_regex=r"^[A-Za-z][A-Za-z0-9_]*$",
    param_categories={"stoich": "Stoichiometry", "rate": "Rates"},
    output_name_regex=r"^[A-Za-z][A-Za-z0-9_]*$",
    output_categories={"pool": "Pools"},
    key_external_outputs=(),
    grouping_axis="pft",
    grouping_axis_dim_name="pft",
    default_groups=(1, 2),
    mechanism_keyword_map={},
    domain_summary="Mock model for adapter-kit end-to-end onboarding tests.",
    parameter_parser_class=None,
    output_parser_class=None,
    source_extensions=(".F90",),
    routine_decl_patterns=(r"\\bsubroutine\\s+(\\w+)",),
    module_file_pattern=r"\\w+Mod\\.F90",
    version_detector_class=None,
    bump_tier_classifier_class=None,
    milestone_label_format="mocktest-{commit_short}",
    milestone_metadata_class=None,
    # ---- distillation field 1/2: input<->binary compat guard ----
    input_reader_sources=("src/ReadInputMod.F90",),
    input_read_pattern=r"getvar\\(\\s*'([A-Za-z0-9_]+)'",
    # ---- distillation field 3/4/5: bounds heuristics ----
    fraction_param_names=("FRACX",),
    fraction_categories=("stoich",),
    signed_param_names=("OFFSET",),
    # ---- distillation field 6: output alignment (flat = grouping axis directly indexable)
    grouping_axis_block_dim_name="",
    # ---- distillation field 7: ensemble run harness ----
    run_length_control_label="nsteps",
)
'''

_BACKEND_PY = '''\
"""Minimal working ModelBackend for the onboarding e2e test."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..base import ModelBackend
from .spec import MOCKTEST_SPEC


class MockTestBackend(ModelBackend):
    spec = MOCKTEST_SPEC

    # ---- parsing ----
    def parse_parameters(self, param_file: Path) -> Dict[str, Any]:
        with open(param_file) as fh:
            raw = json.load(fh)
        # {name: {default_values, category}} — the shape model_generate_bounds expects.
        return dict(raw)

    def parse_outputs(self, output_cdl: Path) -> Dict[str, Any]:
        return {}

    # ---- param file I/O ----
    def write_parameter_file(self, base_param_file, modifications, output_path) -> None:
        with open(base_param_file) as fh:
            data = json.load(fh)
        for name, val in modifications.items():
            data.setdefault(name, {})["default_values"] = [val]
        with open(output_path, "w") as fh:
            json.dump(data, fh)

    # ---- case creation / submission ----
    def create_case(self, case_name, param_file, config) -> Path:
        p = Path(config.get("case_root", ".")) / case_name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def submit_ensemble(self, case_paths, config) -> List[str]:
        return [f"mock-{i}" for i, _ in enumerate(case_paths)]

    def check_case_status(self, case_path: Path) -> str:
        return "COMPLETED"

    # ---- extraction ----
    def extract_history_variables(self, case_path, variables, time_range=None,
                                  tape: str = "h0") -> Any:
        with open(Path(case_path) / "mock_tape.json") as fh:
            data = json.load(fh)
        return {v: np.asarray(data[v]) for v in variables if v in data}

    # ---- diagnostics ----
    def list_diagnostic_tools(self) -> List[Path]:
        return []
'''

_INIT_PY = '''\
"""Mock adapter package (adapter-kit onboarding e2e test)."""
from __future__ import annotations
from .backend import MockTestBackend
from .spec import MOCKTEST_SPEC
from .. import registry

registry.register_model(MockTestBackend())

__all__ = ["MOCKTEST_SPEC", "MockTestBackend"]
'''


@pytest.fixture(scope="module")
def mock_model(tmp_path_factory):
    """Materialize models/mocktest/ + synthetic data; tear it all down after."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    (MODEL_DIR / "__init__.py").write_text(_INIT_PY)
    (MODEL_DIR / "spec.py").write_text(_SPEC_PY)
    (MODEL_DIR / "backend.py").write_text(_BACKEND_PY)

    data = tmp_path_factory.mktemp("mocktest_data")

    # --- synthetic binary source: reads 3 vars via getvar('...') ---
    src = data / "checkout" / "src"
    src.mkdir(parents=True)
    (src / "ReadInputMod.F90").write_text(
        "subroutine ReadInput\n"
        "  call getvar('VCMX')\n"
        "  call getvar('CNLF')\n"
        "  call getvar('IEBTYP')   ! added by a newer binary\n"
        "end subroutine\n"
    )

    # --- COMPATIBLE input: has all 3 required vars (+ bounds-relevant ones) ---
    full = {
        "VCMX":   {"default_values": [50.0], "category": "rate"},
        "CNLF":   {"default_values": [25.0], "category": "stoich"},
        "IEBTYP": {"default_values": [1],    "category": "rate"},
        "FRACX":  {"default_values": [0.4],  "category": "stoich"},
        "OFFSET": {"default_values": [-2.0], "category": "rate"},
    }
    (data / "params_full.json").write_text(json.dumps(full))

    # --- INCOMPATIBLE input: missing IEBTYP (older-than-binary input) ---
    old = {k: v for k, v in full.items() if k != "IEBTYP"}
    (data / "params_old.json").write_text(json.dumps(old))

    # --- synthetic completed case: a (time=4, pft=2) tape ---
    case = data / "case1"
    case.mkdir()
    (case / "mock_tape.json").write_text(json.dumps({
        "LEAF_C_pft": [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0], [4.0, 40.0]],
        "GPP_col":    [0.5, 0.6, 0.7, 0.8],
    }))

    # import (self-registers the backend)
    sys.path.insert(0, str(REPO))
    importlib.invalidate_caches()
    importlib.import_module("models.mocktest")

    yield {"data": data, "case": case}

    # teardown: drop the package + purge from sys.modules + registry
    for mod in [m for m in sys.modules if m == "models.mocktest" or m.startswith("models.mocktest.")]:
        del sys.modules[mod]
    try:
        from models import registry
        registry._MODELS.pop("mocktest", None)
    except Exception:
        pass
    shutil.rmtree(MODEL_DIR, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 1. Input<->binary version-compat guard (tools/model_check_input_compat.py)
# --------------------------------------------------------------------------- #

def test_input_compat_compatible(mock_model):
    """Full input has every var the binary reads → exit 0 COMPATIBLE."""
    r = subprocess.run(
        [PYBIN, "tools/model_check_input_compat.py", "--model", "mocktest",
         "--checkout", str(mock_model["data"] / "checkout"),
         "--param-file", str(mock_model["data"] / "params_full.json")],
        cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "COMPATIBLE" in r.stdout


def test_input_compat_incompatible(mock_model):
    """Old input missing IEBTYP → exit 2 INCOMPATIBLE, names the missing var."""
    r = subprocess.run(
        [PYBIN, "tools/model_check_input_compat.py", "--model", "mocktest",
         "--checkout", str(mock_model["data"] / "checkout"),
         "--param-file", str(mock_model["data"] / "params_old.json")],
        cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "INCOMPATIBLE" in r.stdout
    assert "IEBTYP" in r.stdout


# --------------------------------------------------------------------------- #
# 2. obs<->sim alignment (tools/model_evaluate_case.py) — library + CLI
# --------------------------------------------------------------------------- #

def test_evaluate_case_library(mock_model):
    """A new model's tape scores through the generic evaluate layer."""
    from tools.model_evaluate_case import evaluate_model_case
    targets = [
        # pft=2, last time step → 40.0, observed 40 → zero error
        {"name": "leaf_pft2", "variable": "LEAF_C_pft", "pft": 2, "time": -1, "observed": 40.0},
        # column-level var, mean over full window
        {"name": "gpp", "variable": "GPP_col", "window": [0, -1], "reduce": "mean", "observed": 0.65},
    ]
    total, errors, sim = evaluate_model_case(
        mock_model["case"], targets, model="mocktest")
    assert sim["leaf_pft2"] == pytest.approx(40.0)
    assert sim["gpp"] == pytest.approx(0.65)
    assert errors["leaf_pft2"] == pytest.approx(0.0, abs=1e-9)
    assert total == pytest.approx(0.0, abs=1e-9)


def test_evaluate_case_cli(mock_model):
    """The CLI dispatches through --model and prints per-target costs."""
    targets = [{"name": "leaf_pft1", "variable": "LEAF_C_pft", "pft": 1, "time": 0, "observed": 1.0}]
    tf = mock_model["data"] / "targets.json"
    tf.write_text(json.dumps(targets))
    r = subprocess.run(
        [PYBIN, "tools/model_evaluate_case.py", "--model", "mocktest",
         str(mock_model["case"]), "--targets", str(tf)],
        cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "leaf_pft1" in r.stdout


def test_reduce_target_negative_window(mock_model):
    """The negative-window edge (hi == -1) that bit EcoSIM: last-of-series, not empty."""
    from tools.model_evaluate_case import reduce_target
    from models.mocktest.backend import MockTestBackend
    be = MockTestBackend()
    extracted = {"GPP_col": np.array([0.5, 0.6, 0.7, 0.8])}
    val = reduce_target(be, extracted, {"variable": "GPP_col", "window": [0, -1], "reduce": "last"})
    assert val == pytest.approx(0.8)


# --------------------------------------------------------------------------- #
# 3. Group-select seam (default flat + block-dim override)
# --------------------------------------------------------------------------- #

def test_select_group_series_flat_default(mock_model):
    """Default flat indexing picks the PFT column for a (time, pft) var."""
    from models.mocktest.backend import MockTestBackend
    be = MockTestBackend()
    data = np.array([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]])
    got = be.select_group_series(data, {"variable": "X", "pft": 2})
    assert list(got) == [10.0, 20.0, 30.0]


def test_select_group_series_block_override(mock_model):
    """A FATES-style block-structured model overrides the seam and it still dispatches."""
    from models.mocktest.backend import MockTestBackend

    class BlockBackend(MockTestBackend):
        BLOCK = 2  # 2 size classes per pft, folded into a flat (time, size*pft) dim

        def select_group_series(self, data, target):
            arr = np.asarray(data)
            pft = int(target["pft"])
            cols = [(pft - 1) * self.BLOCK + s for s in range(self.BLOCK)]
            return arr[:, cols].sum(axis=1)

    be = BlockBackend()
    # 2 pft x 2 size = 4 flat cols; pft1=cols0,1  pft2=cols2,3
    data = np.array([[1.0, 1.0, 5.0, 5.0], [2.0, 2.0, 6.0, 6.0]])
    got = be.select_group_series(data, {"variable": "SZPF", "pft": 2})
    assert list(got) == [10.0, 12.0]


# --------------------------------------------------------------------------- #
# 4. Bounds heuristics (scripts/model_generate_bounds._bounds)
# --------------------------------------------------------------------------- #

def test_bounds_fraction_clamped(mock_model):
    """A fraction param is clamped to [0,1]; a signed param may go negative."""
    from scripts.model_generate_bounds import _bounds
    spec_frac_params = ("FRACX",)
    spec_frac_cats = ("stoich",)
    spec_signed = ("OFFSET",)

    lo, hi, _ = _bounds("FRACX", "stoich", 0.4, 0.5, spec_frac_params, spec_frac_cats, spec_signed)
    assert lo >= 0.0 and hi <= 1.0

    # signed param with a default of -2.0 must NOT be clamped up to >= 0
    lo2, hi2, _ = _bounds("OFFSET", "rate", -2.0, 0.5, spec_frac_params, spec_frac_cats, spec_signed)
    assert lo2 < 0.0

    # an ordinary positive rate param is clamped at 0 on the low side, unbounded high
    lo3, hi3, _ = _bounds("VCMX", "rate", 50.0, 0.5, spec_frac_params, spec_frac_cats, spec_signed)
    assert lo3 >= 0.0 and hi3 > 50.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
