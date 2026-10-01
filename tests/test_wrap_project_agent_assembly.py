"""wrap_for_project_agent.sh builds a project repo with BOTH hook layers live and the right assets.

visibility: public

Three properties, each of which failed silently before it was tested:

  * the framework's Claude Code hooks are REGISTERED in the project repo, not merely copied there,
    and the project's own registrations survive a refresh;
  * a destination inside another git repository is refused, because the script would otherwise
    configure and commit into that outer repository;
  * --init requires --models, and everything model-scoped follows it: rag/ (its code,
    milestones.json, rag/data/), each model's graphs (rag/graphs/<model>*.json), vector index and
    metadata, and the per-model files inside use_cases/TEMPLATE/. A project gets its own models'
    knowledge and none of another's.

SAFETY. pytest's temp dir lives inside this repository, so a regression in the nesting guard could
commit into it. Every run therefore sets GIT_CEILING_DIRECTORIES to the test's own temp dir, so git
cannot see past it, and the nesting case builds its own throwaway outer repository to be inside.

The source is a minimal FAKE release: the real wrap scripts, hooks, settings file and TEMPLATE/,
plus a small synthetic rag/. The script refuses a development clone as its source, so it cannot be
pointed at this one.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FRAMEWORK = "${CLAUDE_PROJECT_DIR}/.claude/hooks/"
ROOT_DOCS = ("CLAUDE.md", "README.md", "AGENTS.md")
MARKER = "<!-- A2MC FRAMEWORK REFERENCE BELOW."


def _fake_release(root: Path) -> Path:
    src = root / "src"
    for rel in ["scripts/wrap_for_project_agent.sh", "scripts/_wrap_scaffold.sh",
                "scripts/_wrap_deregister.py", "scripts/_wrap_merge_settings.py",
                "scripts/_wrap_root_docs.py",
                "tools/skill_models.py", ".claude/settings.json"]:
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, src / rel)
    shutil.copytree(REPO / ".claude" / "hooks", src / ".claude" / "hooks",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (src / ".claude" / "skills").mkdir(parents=True)
    shutil.copytree(REPO / "use_cases" / "TEMPLATE", src / "use_cases" / "TEMPLATE")
    rag = src / "rag"
    for d in ["data", "graphs", "metadata", "chroma_db/ecosim-abc", "chroma_db/pflotran-def"]:
        (rag / d).mkdir(parents=True, exist_ok=True)
    (rag / "loader.py").write_text("# rag code\n")
    (rag / "milestones.json").write_text('{"milestones": {}}\n')
    (rag / "data" / "curated.yaml").write_text("x: 1\n")
    for p in ["api-43-1", "ecosim-abc", "pflotran-def"]:
        (rag / "graphs" / (p + ".json")).write_text("{}\n")
    for p in ["ecosim-abc", "pflotran-def"]:
        (rag / "metadata" / (p + ".json")).write_text("{}\n")
        (rag / "chroma_db" / p / "chroma.sqlite3").write_text("index\n")
    (src / "VERSION").write_text("test\n")
    for doc in ROOT_DOCS:
        (src / doc).write_text("# Framework %s\n\nThe framework's own %s, version one.\n" % (doc, doc))
    # A model-scoped skill and a skill table naming it, so de-registration is exercised on the
    # copied root documents -- including a row that only MENTIONS it, which must survive.
    sk = src / ".claude" / "skills" / "pflotran-only"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: pflotran-only\ndescription: x\nmodes:\n  scope: [pflotran]\n---\n")
    for doc in ("CLAUDE.md", "AGENTS.md"):
        with open(src / doc, "a") as f:
            f.write("\n| skill | when |\n|---|---|\n| `pflotran-only` | pflotran work |\n"
                    "| `phase5-testing` | routes to `pflotran-only` |\n")
    return src


def _work(ceiling: Path) -> Path:
    """Build BELOW the ceiling: git will not climb into the ceiling directory, but a search that
    starts AT it still looks further up, which here is this repository."""
    w = ceiling / "work"
    w.mkdir(exist_ok=True)
    return w


def _env(ceiling: Path) -> dict:
    e = dict(os.environ)
    e.update(GIT_CEILING_DIRECTORIES=str(ceiling), A2MC_PYTHON=sys.executable,
             GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
             GIT_COMMITTER_EMAIL="t@t")
    return e


def _wrap(src: Path, ceiling: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(src / "scripts" / "wrap_for_project_agent.sh")] + list(args),
                          capture_output=True, text=True, timeout=300, env=_env(ceiling))


def _commands(settings: Path) -> set:
    d = json.loads(settings.read_text())
    return {h["command"] for gs in d.get("hooks", {}).values() for g in gs for h in g.get("hooks", [])}


@pytest.fixture
def built(tmp_path):
    src = _fake_release(tmp_path)
    dest = _work(tmp_path) / "A2MC-Demo"
    r = _wrap(src, tmp_path, "--init", "--project", "Demo", "--dest", str(dest), "--models", "ecosim",
              "--calibration", "yes")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return src, dest, tmp_path


def test_framework_hooks_are_registered_not_just_copied(built):
    src, dest, _ = built
    have = _commands(dest / ".claude" / "settings.json")
    framework = _commands(src / ".claude" / "settings.json")
    assert framework and framework <= have, sorted(framework - have)
    assert any("/Demo/.claude/hooks/session-start.py" in c for c in have), have


def test_refresh_restores_framework_hooks_and_keeps_the_projects(built):
    src, dest, ceiling = built
    f = dest / ".claude" / "settings.json"
    d = json.loads(f.read_text())
    dropped = None
    for gs in d["hooks"].values():                      # remove one framework registration
        for g in gs:
            for h in list(g["hooks"]):
                if FRAMEWORK in h["command"] and dropped is None:
                    dropped = h["command"]
                    g["hooks"].remove(h)
    extra = 'python3 "${CLAUDE_PROJECT_DIR}/Demo/.claude/hooks/extra.py"'
    d["hooks"].setdefault("Stop", []).append({"hooks": [{"type": "command", "command": extra}]})
    f.write_text(json.dumps(d, indent=2) + "\n")
    subprocess.run(["git", "-C", str(dest), "commit", "-qam", "Edit settings", "--no-verify"],
                   check=True, env=_env(ceiling))
    r = _wrap(src, ceiling, "--refresh", "--dest", str(dest))
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    have = _commands(f)
    assert dropped in have, "a framework hook removed downstream was not restored"
    assert extra in have, "the project's own hook was lost on refresh"


def test_a_destination_inside_another_repository_is_refused(tmp_path):
    src = _fake_release(tmp_path)
    outer = _work(tmp_path) / "outer"
    outer.mkdir()
    subprocess.run(["git", "init", "-q", str(outer)], check=True, env=_env(tmp_path))
    r = _wrap(src, tmp_path, "--init", "--project", "Demo", "--dest", str(outer / "dest"),
              "--models", "ecosim", "--calibration", "yes")
    assert r.returncode != 0
    assert "inside the git repository" in r.stderr, r.stderr
    got = subprocess.run(["git", "-C", str(outer), "config", "core.hooksPath"],
                         capture_output=True, text=True, env=_env(tmp_path)).stdout.strip()
    assert got == "", "the outer repository's hooks path was changed: %r" % got
    assert not (outer / "dest").exists()


def test_rag_code_is_universal_and_each_profile_travels_only_with_its_model(built):
    _, dest, _ = built
    assert (dest / "rag" / "loader.py").is_file() and (dest / "rag" / "milestones.json").is_file()
    assert (dest / "rag" / "data" / "curated.yaml").is_file()
    graphs = sorted(p.name for p in (dest / "rag" / "graphs").iterdir())
    assert graphs == ["ecosim-abc.json"], "an EcoSIM project got another model's graph: %s" % graphs
    assert sorted(p.name for p in (dest / "rag" / "metadata").iterdir()) == ["ecosim-abc.json"]
    assert sorted(p.name for p in (dest / "rag" / "chroma_db").iterdir()) == ["ecosim-abc"]


def test_init_refuses_without_models(tmp_path):
    """A project names the models it works with; that choice decides everything model-scoped."""
    src = _fake_release(tmp_path)
    dest = _work(tmp_path) / "A2MC-None"
    r = _wrap(src, tmp_path, "--init", "--project", "Demo", "--dest", str(dest), "--calibration", "yes")
    assert r.returncode != 0
    assert "--init requires --models" in r.stderr, r.stderr
    assert not dest.exists()


def test_template_model_files_follow_models(built):
    _, dest, _ = built
    t = dest / "use_cases" / "TEMPLATE"
    names = {p.name for p in t.rglob("*") if p.is_file()}
    assert "ecosim_template_config.sh" in names and "ecosim_template_readme.md" in names
    assert not [n for n in names if n.startswith(("fates_template", "pflotran_template"))], names
    assert (t / "case_template").is_dir(), "case_template/ is generic and must survive the filter"
    assert (t / "README.md").is_file()


# --------------------------------------------------------------- the root documents, by calibration

def _commit(dest: Path, ceiling: Path, msg: str):
    subprocess.run(["git", "-C", str(dest), "add", "-A"], check=True, env=_env(ceiling))
    subprocess.run(["git", "-C", str(dest), "commit", "-qm", msg, "--no-verify"], check=True,
                   env=_env(ceiling))


def test_init_refuses_without_calibration(tmp_path):
    src = _fake_release(tmp_path)
    dest = _work(tmp_path) / "A2MC-X"
    r = _wrap(src, tmp_path, "--init", "--project", "Demo", "--dest", str(dest), "--models", "ecosim")
    assert r.returncode != 0 and "--init requires --calibration" in r.stderr, r.stderr
    assert not dest.exists()


def test_calibrating_project_copies_the_framework_docs_under_its_banner(built):
    _, dest, _ = built
    for doc in ROOT_DOCS:
        text = (dest / doc).read_text()
        assert text.count(MARKER) == 1, doc
        banner, below = text.split(MARKER, 1)
        assert "Demo" in banner, "%s: the project banner is missing above the marker" % doc
        assert "The framework's own %s, version one." % doc in below, doc
    assert "calibration: yes" in (dest / "Demo" / "SEPARATION_MANIFEST.yaml").read_text()


def test_refresh_keeps_the_banner_and_replaces_the_reference(built):
    src, dest, ceiling = built
    f = dest / "AGENTS.md"
    banner, below = f.read_text().split(MARKER, 1)
    f.write_text(banner + "A line the project wrote in its banner.\n\n" + MARKER + below)
    _commit(dest, ceiling, "Write the banner")
    (src / "AGENTS.md").write_text("# Framework AGENTS.md\n\nThe framework's own AGENTS.md, version two.\n")
    r = _wrap(src, ceiling, "--refresh", "--dest", str(dest))
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    text = f.read_text()
    assert "A line the project wrote in its banner." in text.split(MARKER, 1)[0]
    assert "version two" in text and "version one" not in text
    assert text.count(MARKER) == 1


def test_non_calibrating_project_writes_its_own_docs(tmp_path):
    src = _fake_release(tmp_path)
    dest = _work(tmp_path) / "A2MC-Own"
    r = _wrap(src, tmp_path, "--init", "--project", "Demo", "--dest", str(dest), "--models", "ecosim",
              "--calibration", "no")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    for doc in ROOT_DOCS:
        text = (dest / doc).read_text()
        assert MARKER not in text and "The framework's own" not in text, doc


def test_a_project_made_before_the_flag_gets_the_reference_appended_once(tmp_path):
    """The existing-project case: hand-written documents, no marker, a manifest with no
    calibration line. One refresh with --calibration yes keeps every word and appends the
    reference; a second changes nothing."""
    src = _fake_release(tmp_path)
    dest = _work(tmp_path) / "A2MC-Old"
    r = _wrap(src, tmp_path, "--init", "--project", "Demo", "--dest", str(dest), "--models", "ecosim",
              "--calibration", "no")
    assert r.returncode == 0, r.stderr
    man = dest / "Demo" / "SEPARATION_MANIFEST.yaml"
    man.write_text("".join(l for l in man.read_text().splitlines(True) if not l.startswith("calibration:")))
    before = {d: (dest / d).read_text() for d in ROOT_DOCS}
    _commit(dest, tmp_path, "A project from before the flag")
    r = _wrap(src, tmp_path, "--refresh", "--dest", str(dest))
    assert r.returncode != 0 and "predates --calibration" in r.stderr, r.stderr
    r = _wrap(src, tmp_path, "--refresh", "--dest", str(dest), "--calibration", "yes")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    once = {d: (dest / d).read_text() for d in ROOT_DOCS}
    for d in ROOT_DOCS:
        assert once[d].startswith(before[d].rstrip()), "%s: the hand-written text was not kept" % d
        assert once[d].count(MARKER) == 1 and "version one" in once[d], d
    assert "calibration: yes" in man.read_text()
    _commit(dest, tmp_path, "First refresh")
    r = _wrap(src, tmp_path, "--refresh", "--dest", str(dest))
    assert r.returncode == 0, r.stderr
    assert {d: (dest / d).read_text() for d in ROOT_DOCS} == once, "a second refresh changed the documents"


def test_a_project_that_adds_calibration_later_is_upgraded(tmp_path):
    """--calibration no at --init, yes at a later --refresh: the hand-written documents become the
    banner word for word, A2MC's own land below one marker, the manifest records the change, and
    the next refresh needs no flag and changes nothing."""
    src = _fake_release(tmp_path)
    dest = _work(tmp_path) / "A2MC-Later"
    r = _wrap(src, tmp_path, "--init", "--project", "Demo", "--dest", str(dest), "--models", "ecosim",
              "--calibration", "no")
    assert r.returncode == 0, r.stderr
    for d in ROOT_DOCS:                                  # the project writes its own, as Step 5b says
        (dest / d).write_text("# Demo %s\n\nThe project's own words about %s.\n" % (d, d))
    _commit(dest, tmp_path, "Hand-written root documents")
    before = {d: (dest / d).read_text() for d in ROOT_DOCS}
    r = _wrap(src, tmp_path, "--refresh", "--dest", str(dest), "--calibration", "yes")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "calibration: no -> yes" in r.stdout, r.stdout[-2000:]
    once = {d: (dest / d).read_text() for d in ROOT_DOCS}
    for d in ROOT_DOCS:
        assert once[d].startswith(before[d].rstrip()), "%s: the hand-written text was not kept" % d
        assert once[d].count(MARKER) == 1 and "version one" in once[d], d
    man = (dest / "Demo" / "SEPARATION_MANIFEST.yaml").read_text()
    assert "calibration: yes" in man and "calibration: no" not in man, man
    assert man.count("composed:") == 1 and man.index("composed:") < man.index("framework_paths:"), man
    _commit(dest, tmp_path, "Upgrade")
    r = _wrap(src, tmp_path, "--refresh", "--dest", str(dest))
    assert r.returncode == 0, r.stderr
    assert {d: (dest / d).read_text() for d in ROOT_DOCS} == once, "a second refresh changed the documents"


def test_turning_calibration_off_is_refused_and_writes_nothing(built):
    src, dest, ceiling = built
    man = dest / "Demo" / "SEPARATION_MANIFEST.yaml"
    before = {p: p.read_text() for p in [man] + [dest / d for d in ROOT_DOCS]}
    r = _wrap(src, ceiling, "--refresh", "--dest", str(dest), "--calibration", "no")
    assert r.returncode != 0 and "would turn it off" in r.stderr, r.stderr
    assert {p: p.read_text() for p in before} == before, "a refused refresh wrote something"


def test_framework_text_without_a_marker_is_refused_not_duplicated(built):
    src, dest, ceiling = built
    f = dest / "README.md"
    f.write_text(f.read_text().replace(MARKER, "<!-- someone deleted the marker -->"))
    _commit(dest, ceiling, "Lose the marker")
    r = _wrap(src, ceiling, "--refresh", "--dest", str(dest))
    assert r.returncode != 0 and "no marker line" in r.stderr, r.stderr


def test_a_dropped_skill_leaves_the_copied_root_docs_first_cell_only(built):
    _, dest, _ = built
    assert not (dest / ".claude" / "skills" / "pflotran-only").exists()
    for doc in ("CLAUDE.md", "AGENTS.md"):
        text = (dest / doc).read_text()
        assert "| `pflotran-only` |" not in text, "%s still registers a dropped skill" % doc
        assert "| `phase5-testing` | routes to `pflotran-only` |" in text, \
            "%s lost a row that only MENTIONS the dropped skill" % doc
