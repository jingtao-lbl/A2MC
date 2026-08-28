"""
test_offline_agent_mode.py — Phase-1 offline interactive agent mode (docs/25).

Covers the mode-aware substrate the ported agent components rely on:
  - describe_mode / config.MODE resolves and renders for representative modes
    (ELM-FATES + ECA, and ELM-only) and reflects nutrient_comp_pathway
  - every shipped SKILL.md has a valid `modes:` frontmatter block
  - the public agent surface (AGENTS.md + .claude/skills/) is leak-clean
    (no private host paths / usernames) — the same gate sync_to_public.sh enforces

Run:
    python -m unittest tests.test_offline_agent_mode -v
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

SKILLS_DIR = _REPO_ROOT / ".claude" / "skills"

# IMPORTED, never re-declared. This file previously carried its own copy of the pattern, which
# silently enforced a stale policy: when the tokens were relaxed in the tool, this test kept
# failing on text the PI had explicitly asked for. A test asserting a contract must read the
# contract, not a snapshot of it. The remaining shell copies are pinned by
# tests/test_leak_tokens_in_sync.py. (2026-08-14)
from tools.validate_agent_surface import LEAK_TOKENS  # noqa: E402


class TestDescribeMode(unittest.TestCase):
    """config.MODE resolves and the summary reflects the active configuration."""

    def _mode(self, elm_options: str):
        os.environ["A2MC_ELM_OPTIONS"] = elm_options
        # config.MODE is a property -> ConfigMode.from_env(); re-reads env each access.
        from tools.config import config
        return config.MODE

    def test_fates_eca(self):
        m = self._mode("-bgc fates -nutrient cnp -nutrient_comp_pathway eca")
        self.assertTrue(m.use_fates)
        self.assertEqual(m.nutrient_comp_pathway, "eca")
        block = m.to_prompt_block()
        self.assertIn("FATES", block)
        self.assertIn("ECA", block.upper())

    def test_elm_only(self):
        m = self._mode("-bgc sp")
        self.assertFalse(m.use_fates)
        block = m.to_prompt_block()
        self.assertIn("FATES DISABLED", block)

    def tearDown(self):
        os.environ.pop("A2MC_ELM_OPTIONS", None)


class TestSkillFrontmatter(unittest.TestCase):
    """Every shipped SKILL.md carries a valid modes: frontmatter block."""

    def _skills(self):
        return sorted(SKILLS_DIR.glob("*/SKILL.md"))

    def test_skills_present(self):
        # Subset check (not exact) so adding skills doesn't break the test; the
        # registry parity is enforced separately by tools/check_skill_registry.py.
        names = {p.parent.name for p in self._skills()}
        expected = {
            "log", "onboard-session", "curate-knowledge", "arm-hpc-monitoring",
            "restart-failed-jobs", "diagnose-forensics", "scientific-analysis",
            "build-rag-from-scratch", "rebuild-rag", "generate-codebase-wiki",
            "validate-rag-chain", "inject-knowledge", "add-skill", "refine-skill",
        }
        missing = expected - names
        self.assertEqual(missing, set(), f"expected skills missing: {missing}")

    def test_modes_frontmatter_valid(self):
        for skill in self._skills():
            text = skill.read_text()
            self.assertTrue(text.startswith("---"), f"{skill} missing frontmatter")
            fm = text.split("---", 2)[1]
            meta = yaml.safe_load(fm)
            self.assertIn("name", meta, f"{skill} missing name")
            self.assertIn("description", meta, f"{skill} missing description")
            self.assertIn("modes", meta, f"{skill} missing modes block")
            modes = meta["modes"]
            self.assertIn("requires_fates", modes, f"{skill} modes missing requires_fates")
            self.assertIsInstance(modes["requires_fates"], bool, f"{skill} requires_fates not bool")
            self.assertIn("nutrient_pathway", modes, f"{skill} modes missing nutrient_pathway")
            self.assertIn(modes["nutrient_pathway"], ("any", "eca", "rd"),
                          f"{skill} bad nutrient_pathway {modes['nutrient_pathway']!r}")

    def test_requires_fates_matches_skill_category(self):
        # requires_fates:true = the skill is only meaningful with FATES. That is now just the two
        # whose PROCEDURE is FATES-shaped: offline-testing-workflow (create_case.sh, chained
        # ADSP/RGSP/TRANS legs) and add-fates-parameter (adds a FATES source parameter).
        #
        # summarize-calibration-round and compare-calibration-rounds were in this set until
        # 2026-08-24 and were made GENERIC that day (PI-directed): they are the standardized
        # round-close deliverables, so gating them on FATES meant no adapter model had one, on the
        # branch whose whole purpose is generalizing A2MC past ELM. Their CONTRACT is now
        # model-agnostic and only the figure/screen BACKEND is per model, resolved via
        # describe_mode. This test caught the drift: the two skills' frontmatter changed and this
        # set did not, and the skill registry checker cannot see it because it does not read modes.
        fates_only = {"offline-testing-workflow", "add-fates-parameter"}
        for skill in self._skills():
            meta = yaml.safe_load(skill.read_text().split("---", 2)[1])
            rf = meta["modes"]["requires_fates"]
            expected = skill.parent.name in fates_only
            self.assertEqual(rf, expected,
                             f"{skill.parent.name}: requires_fates={rf}, expected {expected}")


class TestAgentSurfaceLeakClean(unittest.TestCase):
    """AGENTS.md + .claude/skills/ contain no private host paths / usernames."""

    def test_no_leak_tokens(self):
        # Scan the shipped surface only; skip gitignored local artifacts (.ipynb_checkpoints)
        # that are never synced to the public repo.
        surface = [_REPO_ROOT / "AGENTS.md"] + [
            f for f in SKILLS_DIR.rglob("*.md") if ".ipynb_checkpoints" not in f.parts]
        offenders = []
        for f in surface:
            for i, line in enumerate(f.read_text().splitlines(), 1):
                if LEAK_TOKENS.search(line):
                    offenders.append(f"{f.relative_to(_REPO_ROOT)}:{i}: {line.strip()}")
        self.assertEqual(offenders, [], "leak tokens in agent surface:\n" + "\n".join(offenders))


class TestAgentSurfaceValidator(unittest.TestCase):
    """tools/validate_agent_surface.py passes on the real surface and fires on pitfalls."""

    def test_real_surface_clean(self):
        from tools.validate_agent_surface import validate_agent_surface
        errors = [f for f in validate_agent_surface(_REPO_ROOT) if f.level == "ERROR"]
        self.assertEqual(errors, [], f"agent surface should validate clean; got {errors}")

    def test_public_contact_is_exempt_but_never_masks_a_real_leak(self):
        """`jingtao@lbl.gov` is published; the bare `jingtao` token targets HOST PATHS.

        Adopted from `main` v2.229-era (`PUBLIC_CONTACT`). The third case is the one worth
        keeping: stripping the address must not blind the scan to a host path sharing the
        SAME line, which is how an exemption turns into a hole.
        """
        import tempfile, shutil
        from tools.validate_agent_surface import validate_agent_surface
        head = ("---\nname: goodskill\ndescription: d\n"
                "modes:\n  requires_fates: false\n---\n")

        def _l1(body):
            d = Path(tempfile.mkdtemp())
            try:
                sk = d / ".claude/skills/goodskill"
                sk.mkdir(parents=True)
                (d / "AGENTS.md").write_text("# A\n")
                (sk / "SKILL.md").write_text(head + body)
                return [f for f in validate_agent_surface(d) if f.code == "L1"]
            finally:
                shutil.rmtree(d)

        self.assertEqual(_l1("Reach the maintainer at jingtao@lbl.gov.\n"), [],
                         "the published contact address is not a leak")
        self.assertTrue(_l1("see ~/x\n"),
                        "a host path must still fire")
        self.assertTrue(_l1("mail jingtao@lbl.gov about ~/x\n"),
                        "stripping the address must NOT mask a host path on the same line")

    def test_fallback_drops_dot_dirs_but_still_catches_real_leaks(self):
        """The non-git fallback (main's v2.230 _on_surface predicate), both directions.

        A tmpdir is not a git repo, so `git ls-files` cannot answer and the fallback runs.
        It must drop a dot-directory autosave (the false positive that cost both branches a
        day on 2026-08-06) WITHOUT going blind to a real leak in the live SKILL.md — a
        narrowed scan and a disabled one look identical from a green run.
        """
        import tempfile, shutil
        from tools.validate_agent_surface import validate_agent_surface
        d = Path(tempfile.mkdtemp())
        try:
            sk = d / ".claude/skills/goodskill"
            sk.mkdir(parents=True)
            (d / "AGENTS.md").write_text("# A\n")
            head = ("---\nname: goodskill\ndescription: d\n"
                    "modes:\n  requires_fates: false\n---\n")
            (sk / "SKILL.md").write_text(head + "# body\n")
            ck = sk / ".ipynb_checkpoints"
            ck.mkdir()
            (ck / "SKILL-checkpoint.md").write_text("leak ~/stale\n")

            codes = {(f.level, f.code) for f in validate_agent_surface(d)}
            self.assertNotIn(("ERROR", "L1"), codes,
                             "a leak inside a dot-directory must NOT fire (gitignored autosave)")
            self.assertIn(("WARN", "G1"), codes,
                          "the non-git fallback must announce itself, not degrade silently")

            # ...and the scan must still be live for the file that actually ships.
            (sk / "SKILL.md").write_text(head + "leak ~/real\n")
            codes = {(f.level, f.code) for f in validate_agent_surface(d)}
            self.assertIn(("ERROR", "L1"), codes,
                          "a real leak in the live SKILL.md must still fire on the fallback")
        finally:
            shutil.rmtree(d)

    def test_pitfalls_fire(self):
        import tempfile
        from tools.validate_agent_surface import validate_agent_surface
        d = Path(tempfile.mkdtemp())
        (d / ".claude/skills/goodskill").mkdir(parents=True)
        (d / "docs/a2mc_reference").mkdir(parents=True)
        (d / "AGENTS.md").write_text(
            "# A\nsee [cat](docs/a2mc_reference/skills_catalog.md)\n"
            "leak ~/x\n[dead](nope/missing.md)\n"
        )
        (d / ".claude/skills/goodskill/SKILL.md").write_text(
            "---\nname: wrongname\ndescription: d\n"
            "modes:\n  requires_fates: notabool\n  nutrient_pathway: banana\n---\n# body\n"
        )
        (d / "docs/a2mc_reference/skills_catalog.md").write_text("# cat\n[phantom](phantom/SKILL.md)\n")
        codes = {(f.level, f.code) for f in validate_agent_surface(d)}
        for need in [("ERROR", "L1"), ("ERROR", "F4"), ("ERROR", "F5"), ("ERROR", "D1")]:
            self.assertIn(need, codes, f"validator failed to fire {need}")
        # Registry/catalog parity (C1/C2) moved to check_skill_registry.py (D1 de-dup, v2.107):
        # validate_agent_surface no longer fires them; check_skill_registry owns that (see
        # TestRegistryAndPhaseDocGates below).
        self.assertNotIn(("ERROR", "C2"), codes)
        self.assertNotIn(("WARN", "C1"), codes)


class TestRegistryAndPhaseDocGates(unittest.TestCase):
    """The ported integrity checkers (v2.107) stay green on the real repo, and the
    registry is genuinely 4-way (disk ↔ README ↔ catalog ↔ AGENTS.md)."""

    def _run(self, script):
        import subprocess
        return subprocess.run([sys.executable, str(_REPO_ROOT / script)],
                              cwd=str(_REPO_ROOT), capture_output=True, text=True)

    def test_skill_registry_clean(self):
        r = self._run("tools/check_skill_registry.py")
        self.assertEqual(r.returncode, 0, f"registry drift:\n{r.stdout}\n{r.stderr}")

    def test_phase_script_docs_clean(self):
        r = self._run("tools/check_phase_script_docs.py")
        self.assertEqual(r.returncode, 0, f"phase script-doc drift:\n{r.stdout}\n{r.stderr}")

    def test_registry_is_four_way(self):
        # AGENTS.md 'At a glance' table is a real 4th registry: 1:1 with skills on disk.
        import importlib
        csr = importlib.import_module("tools.check_skill_registry")
        disk = set(csr.skills_on_disk())
        self.assertEqual(csr.agents_table_names(), disk,
                         "AGENTS.md 'At a glance' table is not 1:1 with skills on disk")
        self.assertEqual(csr.readme_table_names(), disk)
        self.assertEqual(csr.catalog_names(), disk)

    def test_contract_and_marker_clean(self):
        # The new contract_check (cited paths/skills exist) + marker_check (balanced
        # <!-- private --> blocks) pass on the real surface.
        import importlib
        csr = importlib.import_module("tools.check_skill_registry")
        self.assertEqual(csr.contract_check(csr.skills_on_disk()), [],
                         "a shipped skill cites a path/skill that does not exist")
        self.assertEqual(csr.marker_check(), [], "unbalanced/inline <!-- private --> markers")

    def test_cited_paths_survives_code_fence(self):
        # Regression (20260702f): a ``` code fence must NOT desync backtick pairing and
        # hide a real path citation that follows it. cited_paths pairs line-by-line.
        import importlib
        csr = importlib.import_module("tools.check_skill_registry")
        fence = "`" * 3
        text = (
            "Intro cites `tools/real_a.py`.\n"
            f"{fence}\n"
            "code with `inline` and `spans` inside a fence\n"
            f"{fence}\n"
            "After the fence, `tools/real_b.py` must still be detected.\n"
        )
        paths = csr.cited_paths(text)
        self.assertIn("tools/real_a.py", paths)
        self.assertIn("tools/real_b.py", paths,
                      "path cited after a code fence was dropped (fence-desync bug)")


class TestExpectedSectionsGapList(unittest.TestCase):
    """The gap list must be able to NAME every section it lists.

    `_offline_supplement` flags a section by testing `f"## {s}" not in content`. A section the
    phase method emits UNCONDITIONALLY therefore can never be flagged — the entry looks like
    coverage and provides none. That is exactly what happened when `Design Decisions` was added
    to phase 0's list on 2026-08-07: `log_design` always emits it with a
    "*No specific decisions recorded*" placeholder, so it never once appeared in the gap list.
    Caught by hand; this makes it mechanical (feedback_a_check_that_cannot_fail).
    """

    def _design_log(self, tmp, **kw):
        os.environ["A2MC_AGENT_MODE"] = "offline"
        try:
            from tools.phase_logger import PhaseLogger
            site = Path(tmp) / "site"
            pl = PhaseLogger(site_dir=str(site), site_name="T",
                             calibration_round=3, experiment_count=0)
            return Path(pl.log_design(title="T", sampling_method="morris",
                                      n_parameters=3, n_simulations=10, **kw)).read_text()
        finally:
            os.environ.pop("A2MC_AGENT_MODE", None)

    def test_no_phase0_expected_section_is_unconditionally_emitted(self):
        """Every listed section must be absent from a minimal log, or it can never be flagged."""
        import tempfile
        from tools.phase_logger import PhaseLogger
        with tempfile.TemporaryDirectory(dir=str(_REPO_ROOT / "tmp")) as d:
            text = self._design_log(d)
            dead = [s for s in PhaseLogger._EXPECTED_SECTIONS[0] if f"## {s}" in text]
        self.assertEqual(
            dead, [],
            f"phase-0 sections {dead} are emitted unconditionally, so the gap list can never "
            "name them. Either make the emission conditional or drop them from "
            "_EXPECTED_SECTIONS[0] — a listed section that cannot be flagged implies coverage "
            "it does not provide.")

    def test_parameter_set_and_bounds_flags_when_omitted_and_carries_when_supplied(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=str(_REPO_ROOT / "tmp")) as d:
            omitted = self._design_log(d)
            supplied = self._design_log(d, parameter_set_changes="DROP VCMX4 -> base value 25.0")
        self.assertNotIn("## Parameter Set and Bounds", omitted,
                         "heading emitted with no content — the gap check would report it as provided")
        self.assertIn("- Parameter Set and Bounds", omitted, "omission was not flagged in the gap list")
        self.assertIn("## Parameter Set and Bounds", supplied)
        self.assertIn("base value 25.0", supplied)
        self.assertNotIn("- Parameter Set and Bounds", supplied,
                         "section was supplied yet still reported as a gap")


if __name__ == "__main__":
    unittest.main(verbosity=2)
