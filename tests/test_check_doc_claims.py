"""`tools/check_doc_claims.py` catches the claim shapes a bare `git grep` cannot.

WRITTEN FAILURE-FIRST (`feedback_a_check_that_cannot_fail`). Each test names the miss it reproduces,
and the two that matter carry their own CONTROL in the same test, because "the scanner reported
nothing" and "the scanner is broken" are the same observation:

  * `test_emphasis_inside_the_phrase_is_caught` -- the real 2026-08-26 miss. `Source **both** before
    every run.` is invisible to `git grep -i 'source both'`. The test asserts BOTH that the scanner
    finds it AND that a literal search does not, so it fails if the scanner ever degrades to a plain
    grep.
  * `test_changelog_section_is_skipped_but_the_body_is_not` -- the same file, the same phrase, above
    and below the heading. A skip that skipped everything would pass a body-only assertion.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "check_doc_claims.py"

REGISTRY = """
exclude_globs:
  - memory/dev_logs*/**
stop_headings:
  - "## changelog"
claims:
  - id: source-both
    retired: "test"
    why: "the site config auto-sources the machine config"
    patterns:
      - "source both"
    allow:
      - "still works and is a no-op"
"""


def git_repo(tmp_path, files: dict) -> Path:
    """A throwaway git repo, because the tool enumerates from git and not from the disk."""
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    (root / "claims.yaml").write_text(REGISTRY)
    return root


def run(root, *extra):
    r = subprocess.run([sys.executable, str(TOOL), "--root", str(root),
                        "--registry", str(root / "claims.yaml"), *extra],
                       capture_output=True, text=True, cwd=root)
    return r.returncode, r.stdout + r.stderr


def literal_grep(root, needle) -> int:
    """What a bare `git grep -i` would have found -- the baseline this tool must beat."""
    r = subprocess.run(["git", "grep", "-i", "-c", needle], cwd=root,
                       capture_output=True, text=True)
    return 0 if r.returncode else sum(int(l.rsplit(":", 1)[1]) for l in r.stdout.split())


# ---------------------------------------------------------------------------- the real misses ---

def test_emphasis_inside_the_phrase_is_caught(tmp_path):
    """THE 2026-08-26 miss: markdown emphasis splits the phrase for a literal matcher."""
    root = git_repo(tmp_path, {"guide.md": "Source **both** before every run.\n"})
    rc, out = run(root)
    assert rc == 1 and "guide.md:1" in out, out
    assert literal_grep(root, "source both") == 0, (
        "CONTROL FAILED: a literal grep DID find it, so this test no longer proves the "
        "normalisation is doing anything")


def test_underscore_variant_is_caught(tmp_path):
    """`_` is italic markup as well as an identifier character; both directions must match."""
    root = git_repo(tmp_path, {"a.md": "you must _source_ _both_ configs\n"})
    rc, out = run(root)
    assert rc == 1, out


def test_backticks_do_not_hide_a_claim(tmp_path):
    root = git_repo(tmp_path, {"a.md": "run `source both` first\n"})
    assert run(root)[0] == 1


# ------------------------------------------------------------------- what must NOT be flagged ---

def test_changelog_section_is_skipped_but_the_body_is_not(tmp_path):
    """A changelog entry quoting the retired wording is correct forever; the body is not.

    Both halves in one test: a skip that skipped the whole file would pass a body-only assertion.
    """
    both = git_repo(tmp_path, {"s.md": "Source both configs.\n\n## Changelog\n- used to say source both\n"})
    rc, out = run(both)
    assert rc == 1, "the BODY hit was missed"
    assert out.count("s.md:") == 1 and "s.md:1" in out, f"changelog line was flagged too:\n{out}"

    only_log = git_repo(tmp_path / "b", {"s.md": "## Changelog\n- used to say source both\n"})
    assert run(only_log)[0] == 0, "a changelog-only file must be clean"


def test_excluded_paths_are_not_scanned(tmp_path):
    """A dev log records what was true when written; rewriting it falsifies it."""
    root = git_repo(tmp_path, {"memory/dev_logs_x/20260101a_L.md": "Source both configs.\n"})
    assert run(root)[0] == 0


def test_allow_pattern_suppresses_only_the_current_wording(tmp_path):
    """And the control: the same line without the allow phrase IS a hit."""
    ok = git_repo(tmp_path, {"a.md": "Source both configs still works and is a no-op.\n"})
    assert run(ok)[0] == 0, "the allow pattern did not suppress the current correct wording"
    bad = git_repo(tmp_path / "b", {"a.md": "Source both configs.\n"})
    assert run(bad)[0] == 1, (
        "CONTROL FAILED: the near-identical line without the allow phrase was also clean, so the "
        "allow is matching everything")


# ------------------------------------------------------------------------------- mechanics ------

def test_enumeration_is_from_git_not_the_disk(tmp_path):
    """A gitignored stray must be invisible; a new untracked file must not be."""
    root = git_repo(tmp_path, {".gitignore": "ignored/\n",
                               "ignored/x.md": "Source both configs.\n"})
    assert run(root)[0] == 0, "a gitignored file was scanned"
    (root / "fresh.md").write_text("Source both configs.\n")
    assert run(root)[0] == 1, "an untracked, non-ignored file was NOT scanned"


def test_ad_hoc_pattern_mode_skips_the_registry(tmp_path):
    root = git_repo(tmp_path, {"a.md": "the frobnicator is required\n"})
    assert run(root)[0] == 0
    rc, out = run(root, "--pattern", "the frobnicator is required")
    assert rc == 1 and "a.md:1" in out, out


def test_missing_registry_is_a_usage_error_not_a_pass(tmp_path):
    """Exit 2, never 0 -- a checker that cannot load its rules must not report success."""
    root = git_repo(tmp_path, {"a.md": "Source both configs.\n"})
    (root / "claims.yaml").unlink()
    rc, out = run(root)
    assert rc == 2, f"expected a usage error, got {rc}: {out}"


def test_staged_mode_sees_only_staged_files(tmp_path):
    root = git_repo(tmp_path, {"a.md": "Source both configs.\n"})
    assert run(root, "--staged")[0] == 0, "nothing is staged yet"
    subprocess.run(["git", "add", "a.md"], cwd=root, check=True)
    assert run(root, "--staged")[0] == 1


# --------------------------------------------------------- the exclusions must actually exclude ---
# All three of these were WRITTEN and INERT until the registry was seeded on 2026-08-26 and reported
# 35 pre-rule reports plus a plan doc as violations. An exclusion that silently matches nothing is
# the same failure class as a grep that silently finds nothing.

DEEP = """
exclude_globs:
  - memory/dev_logs*/**
  - use_cases/*/reports/**
  - docs/[0-9][0-9]_*.md
stop_headings: []
claims:
  - id: c
    retired: t
    why: w
    patterns: ["source both"]
"""


def test_double_star_excludes_at_ANY_depth(tmp_path):
    """`pathlib.PurePath.match` treats `**` as ONE component, so the deep exclusions were inert."""
    root = git_repo(tmp_path, {
        "memory/dev_logs_x/L.md": "Source both configs.\n",                 # one level
        "memory/dev_logs_x/reflection/L.md": "Source both configs.\n",      # two -- the miss
        "use_cases/C/reports/D/r.md": "Source both configs.\n",             # two -- the miss
    })
    (root / "claims.yaml").write_text(DEEP)
    rc, out = run(root)
    assert rc == 0, f"a deep path was scanned despite its exclusion:\n{out}"


def test_character_class_in_a_glob_is_not_escaped(tmp_path):
    """`docs/[0-9][0-9]_*.md` must match `docs/19_Plan.md`; escaping the class made it literal."""
    root = git_repo(tmp_path, {"docs/19_Plan.md": "Source both configs.\n"})
    (root / "claims.yaml").write_text(DEEP)
    assert run(root)[0] == 0, "the dated-plan exclusion did not match"
    # CONTROL: a doc that is NOT a dated plan is still scanned, so the exclusion is not swallowing all
    (root / "docs" / "live.md").write_text("Source both configs.\n")
    assert run(root)[0] == 1, "CONTROL FAILED: the exclusion is matching everything under docs/"


SCOPED = """
exclude_globs: []
stop_headings: []
claims:
  - id: scoped
    retired: t
    why: w
    only: ['.claude/skills/**', 'docs/**']
    patterns: ["reader's key"]
"""


def test_only_scopes_a_claim_to_the_surfaces_it_governs(tmp_path):
    """A report-contract claim must not reach into a case's own documents.

    Both halves: in scope it fires, out of scope it does not. A scope that matched nothing would
    pass the second assertion alone.
    """
    root = git_repo(tmp_path, {
        "docs/guide.md": "## Reader's key\n",                        # in scope
        "use_cases/C/research_plan.md": "## Reader's key\n",         # out of scope
    })
    (root / "claims.yaml").write_text(SCOPED)
    rc, out = run(root)
    assert rc == 1 and "docs/guide.md" in out, f"the in-scope hit was missed:\n{out}"
    assert "research_plan" not in out, f"the claim reached outside its `only:` scope:\n{out}"


# ------------------------------------------------------------------ the banner is load-bearing ---

BANNERED = """
exclude_globs: []
stop_headings: []
retired_markers: ["**superseded", "**retired"]
claims:
  - id: c
    retired: t
    why: w
    patterns: ["source both"]
"""


def test_a_superseded_banner_silences_the_whole_file(tmp_path):
    """A doc that DECLARES itself history is skipped -- and the control proves the banner did it.

    Both halves in one test: without the banner the same body is a hit. A registry that had simply
    stopped matching would pass a banner-only assertion.
    """
    body = "line one\n\nSource both configs.\n"
    root = git_repo(tmp_path, {"plan.md": "# Plan\n\n> **SUPERSEDED 2026-08-26.** read X instead\n" + body})
    (root / "claims.yaml").write_text(BANNERED)
    assert run(root)[0] == 0, "the banner did not silence the file"

    plain = git_repo(tmp_path / "b", {"plan.md": "# Plan\n\n" + body})
    (plain / "claims.yaml").write_text(BANNERED)
    assert run(plain)[0] == 1, (
        "CONTROL FAILED: the same body without a banner was also clean, so the pass above proves "
        "nothing about the banner")


def test_a_banner_must_be_in_the_HEADER_not_buried(tmp_path):
    """Bounded to the first BANNER_LINES lines.

    Otherwise a passing mention of the word deep inside a LIVE document silently switches the whole
    file off -- a checker that can be disabled by an unrelated sentence is worse than none.
    """
    deep = "filler\n" * 30 + "> **SUPERSEDED** (mentioned in passing)\n\nSource both configs.\n"
    root = git_repo(tmp_path, {"live.md": deep})
    (root / "claims.yaml").write_text(BANNERED)
    assert run(root)[0] == 1, "a banner buried 30 lines down disabled the whole file"


# ------------------------------------------------------------------------------ regression ------

def test_the_live_surface_is_clean():
    """This repo passes its own registry today. Fails the moment a retired claim comes back."""
    r = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "file(s) scanned" in r.stdout
    n = int(re.search(r"\((\d+) file\(s\) scanned\)", r.stdout).group(1))
    assert n > 500, f"only {n} files scanned -- the enumeration is broken, so this proved nothing"
