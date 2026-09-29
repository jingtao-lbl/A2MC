"""tools/session_tmpdir.py: the TMPDIR a Claude Code session in this clone gives the agent's shell.

The SessionStart hook WRITES it to $CLAUDE_ENV_FILE; the write guard and the clone checker READ it
back by session id, because a hook process never sees the exported value. Writer and reader are two
halves of one contract, so the central test here is the round trip: whatever the writer emits, the
reader must recover exactly, or the guard refuses legal work and the checker reports a failure that
is not there.

visibility: public

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import session_tmpdir as S  # noqa: E402

NERSC = {"NERSC_HOST": "perlmutter"}


def _env_file(tmp_path, sid):
    d = tmp_path / "config" / "session-env" / sid
    d.mkdir(parents=True)
    return d / "sessionstart-hook-0.sh"


def test_the_writer_and_the_reader_agree(tmp_path):
    """The round trip. The target is the real clone, which lives inside $HOME on NERSC."""
    env_file = _env_file(tmp_path, "sid-1")
    path, why = S.export_for_session(REPO, str(env_file), NERSC)
    assert why is None and path == S.repo_tmpdir(REPO)
    got = S.session_tmpdir("sid-1", {"CLAUDE_CONFIG_DIR": str(tmp_path / "config")})
    assert got == path
    assert S.inside_home(got)


def test_a_path_with_a_space_survives_the_round_trip(tmp_path):
    """The writer shell-quotes; the reader must unquote, or a clone path with a space breaks."""
    root = Path.home() / "A2MC with space"
    env_file = _env_file(tmp_path, "sid-2")
    env_file.write_text("export TMPDIR='%s/tmp'\n" % root)
    assert S.session_tmpdir("sid-2", {"CLAUDE_CONFIG_DIR": str(tmp_path / "config")}) == \
        str(root / "tmp")


def test_the_writer_does_nothing_off_NERSC_or_without_an_env_file(tmp_path):
    env_file = _env_file(tmp_path, "sid-3")
    assert S.export_for_session(REPO, str(env_file), {})[0] is None
    assert S.export_for_session(REPO, "", NERSC)[0] is None
    assert not env_file.exists()


def test_the_writer_refuses_a_clone_outside_HOME(tmp_path):
    """Exporting an illegal directory would turn the guard's refusal into permission."""
    env_file = _env_file(tmp_path, "sid-4")
    path, why = S.export_for_session(os.sep + "var" + os.sep + "spool", str(env_file), NERSC)
    assert path is None and "outside $HOME" in why
    assert not env_file.exists()


def test_the_reader_finds_nothing_for_another_session_or_a_malformed_id(tmp_path):
    env_file = _env_file(tmp_path, "sid-5")
    env_file.write_text("export TMPDIR=%s\n" % (Path.home() / "x"))
    cfg = {"CLAUDE_CONFIG_DIR": str(tmp_path / "config")}
    assert S.session_tmpdir("sid-6", cfg) is None
    assert S.session_tmpdir("", cfg) is None
    assert S.session_tmpdir("../sid-5", cfg) is None


def test_the_export_wins_over_the_inherited_value(tmp_path):
    env_file = _env_file(tmp_path, "sid-7")
    env_file.write_text("export TMPDIR=%s\n" % (Path.home() / "x"))
    environ = {"CLAUDE_CONFIG_DIR": str(tmp_path / "config"), "TMPDIR": os.sep + "tmp"}
    assert S.effective_tmpdir("sid-7", environ) == str(Path.home() / "x")
    assert S.effective_tmpdir("sid-8", environ) == os.sep + "tmp"


def test_the_SessionStart_hook_exports_BEFORE_it_reports_the_clone_rows():
    """clone_setup() reads this session's export; called first, it would report a failure the
    hook was about to fix."""
    src = (REPO / ".claude" / "hooks" / "session-start.py").read_text()
    body = src[src.index("def main():"):]
    assert "session_tmpdir(root)" in body
    assert body.index("session_tmpdir(root)") < body.index("clone_setup(root")
