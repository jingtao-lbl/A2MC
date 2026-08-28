"""Guards for the two fixes cherry-picked from `main` on 2026-08-07.

Neither fix had a test on `main` (checked across every file in its `tests/`), so the
guards are authored here. Both assert the layer that was actually broken:

1. `success_criteria` was NEVER the logger's bug -- `phase_logger.log_hypothesis()`
   has always accepted and emitted it. The defect was that neither CALLER passed the
   kwarg, so the `if success_criteria:` block never fired and the falsification
   threshold reached no Phase-4 log. A test that calls `log_hypothesis()` directly
   therefore passes both before AND after the fix: it exercises the working layer.
   The regression guard has to read the call sites, so that is what it does.

2. `_reasoning_chain` rendered a bare dangling dash for any evidence entry carrying
   only meta keys -- which looks like a broken renderer rather than a missing summary.
   Measured on the live EcoSIM_BioCON R1 state: 21 of 21 entries.
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from tools.phase_logger import PhaseLogger  # noqa: E402


def _tmpdir():
    """A TemporaryDirectory under the repo-local `tmp/` (NERSC forbids writes outside home).

    `tmp/` is gitignored, so it is absent in a fresh clone. Under pytest that is handled by
    `conftest.pytest_configure`, which mkdirs the `--basetemp` parent — but this module is
    also directly runnable via its `unittest.main()` block, where no conftest runs and
    `tempfile` would raise FileNotFoundError. Create it here so both paths work.
    """
    root = _REPO_ROOT / "tmp"
    root.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=str(root))


def _passes_success_criteria(path: Path) -> bool:
    """True if some `log_hypothesis(...)` call in `path` passes `success_criteria=`."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name != "log_hypothesis":
            continue
        if any(kw.arg == "success_criteria" for kw in node.keywords):
            return True
    return False


class TestFalsificationBarReachesTheLog(unittest.TestCase):
    """The bug was in the callers, so assert the callers."""

    CALL_SITES = (
        Path("orchestrator.py"),
        Path("phases/phase4_hypothesis/synthesis.py"),
    )

    def test_every_log_hypothesis_call_site_passes_success_criteria(self):
        missing = [
            str(p) for p in self.CALL_SITES
            if not _passes_success_criteria(_REPO_ROOT / p)
        ]
        self.assertEqual(
            missing, [],
            "log_hypothesis() called without success_criteria= in: "
            f"{missing}. The logger emits it under `if success_criteria:`, so an "
            "omitted kwarg silently drops the falsification threshold from the log.",
        )

    def test_the_detector_can_actually_fail(self):
        """Mutation check: the AST probe must reject a call that omits the kwarg.

        Without this, a probe that always returned True would look identical to a
        passing suite.
        """
        with _tmpdir() as d:
            bad = Path(d) / "bad.py"
            bad.write_text("logger.log_hypothesis(title='t', mechanism='m')\n")
            self.assertFalse(_passes_success_criteria(bad))
            good = Path(d) / "good.py"
            good.write_text("logger.log_hypothesis(title='t', success_criteria={})\n")
            self.assertTrue(_passes_success_criteria(good))


class TestReasoningChainRendersHonestly(unittest.TestCase):
    """A meta-only entry must say so, not render as a dangling dash."""

    def _chain(self, tmp: Path, evidence: dict) -> str:
        site = tmp / "site"
        (site / "memory").mkdir(parents=True, exist_ok=True)
        (site / "memory" / "workflow_state_offline_r01.json").write_text(
            json.dumps({"evidence": evidence})
        )
        pl = PhaseLogger(site_dir=str(site), site_name="T",
                         calibration_round=1, experiment_count=1)
        return pl._reasoning_chain()

    def test_meta_only_entry_is_marked_not_left_blank(self):
        with _tmpdir() as d:
            out = self._chain(Path(d), {"diagnoses": [
                {"stem": "s1", "log_path": "p", "artifact_dir": "a", "one_line": ""}
            ]})
            self.assertIn("_(no summary recorded)_", out)
            entry = [l for l in out.split("\n") if l.startswith("- `s1`")][0]
            self.assertFalse(entry.rstrip().endswith("—"),
                             "entry rendered as a dangling dash, the pre-fix behaviour")

    def test_one_line_is_rendered_when_present(self):
        """add_evidence() writes `one_line`; the renderer must read it."""
        with _tmpdir() as d:
            out = self._chain(Path(d), {"diagnoses": [
                {"stem": "s1", "log_path": "p", "one_line": "the actual finding"}
            ]})
            self.assertIn("the actual finding", out)
            self.assertNotIn("_(no summary recorded)_", out)

    def test_testing_bucket_is_read_as_well_as_experiments(self):
        """State files have used both names; neither may be silently dropped."""
        with _tmpdir() as d:
            out = self._chain(Path(d), {
                "experiments": [{"stem": "e1", "one_line": "from experiments"}],
                "testing": [{"stem": "t1", "one_line": "from testing"}],
            })
            self.assertIn("from experiments", out)
            self.assertIn("from testing", out)


if __name__ == "__main__":
    unittest.main()
