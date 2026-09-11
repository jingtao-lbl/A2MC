"""`tools/binary_archive_manifest.py` — the manifest detects loss and alteration.

The gap this closes: archived model binaries live outside git (25 MB each, and a fork of an
upstream scientific code should not carry them), so *nothing recorded they existed*. Every SHA256
sat only inside a `PROVENANCE.txt` that was itself gitignored, which meant a deleted or silently
altered archive would be discovered by a run failing, and the `model_change_ledger` entries naming
those binaries were assertions nobody could check.

The binaries are not regenerable: a recompile can perturb floating point, so a rebuilt binary is a
different artifact. That is what makes detection matter rather than being a tidiness concern.

Written failure-first (`feedback_a_check_that_cannot_fail`). These tests drive the module's own
functions against a synthetic archive tree rather than the real one, so they never depend on CFS.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "_bam", ROOT / "tools" / "binary_archive_manifest.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BAM = _mod()


def make_archive(tmp_path, label="R9_test_abc1234", content=b"fake-binary",
                 sha_in_provenance="match"):
    """Build a synthetic archive dir. `sha_in_provenance`: match | wrong | absent."""
    root = tmp_path / "build_archive"
    d = root / label
    d.mkdir(parents=True, exist_ok=True)
    binp = d / "ecosim.f90.x"
    binp.write_bytes(content)
    real = hashlib.sha256(content).hexdigest()
    sha = {"match": real, "wrong": "b" * 64}.get(sha_in_provenance)
    prov = [f"EcoSIM binary archive — {label}",
            "Archived : 2026-08-25 00:00:00",
            "Source   : branch exp/test @ abc1234",
            "Change   : a synthetic archive for tests",
            f"Binary   : ecosim.f90.x   {len(content)} bytes"]
    if sha:
        prov.append(f"SHA256   : {sha}")
    (d / "PROVENANCE.txt").write_text("\n".join(prov) + "\n")
    return root, real


def point_at(monkeypatch, tmp_path, root):
    monkeypatch.setitem(BAM.ARCHIVES, "ecosim", {
        "archive_root": str(root),
        "manifests": [tmp_path / "manifest.json"],
        "binary_name": "ecosim.f90.x",
    })
    return tmp_path / "manifest.json"


# ------------------------------------------------------------------ generate

def test_generate_records_the_real_hash(tmp_path, monkeypatch):
    root, real = make_archive(tmp_path)
    man = point_at(monkeypatch, tmp_path, root)
    assert BAM.cmd_generate(["ecosim"], "2026-08-25") == 0
    entry = json.loads(man.read_text())["archives"][0]
    assert entry["sha256"] == real
    assert entry["provenance_sha256"] == real


def test_generate_on_an_empty_root_is_an_error_not_a_pass(tmp_path, monkeypatch):
    """Anti-silent-pass: 'no archives found' must not write a cheerful empty manifest."""
    root = tmp_path / "build_archive"
    root.mkdir()
    point_at(monkeypatch, tmp_path, root)
    assert BAM.cmd_generate(["ecosim"], "2026-08-25") == 2


# ------------------------------------------------------------------ verify: the failures

def test_M1_an_archive_missing_from_disk_is_an_ERROR(tmp_path, monkeypatch):
    """The case that matters most: every round citing that binary loses its provenance."""
    root, _ = make_archive(tmp_path)
    man = point_at(monkeypatch, tmp_path, root)
    BAM.cmd_generate(["ecosim"], "2026-08-25")
    import shutil
    shutil.rmtree(root / "R9_test_abc1234")
    assert BAM.cmd_verify(["ecosim"]) == 2


def test_M2_an_ALTERED_binary_is_an_ERROR(tmp_path, monkeypatch):
    """An archived binary is supposed to be immutable. A changed hash means altered or swapped —
    which is exactly the shared-build-tree hazard the archive exists to prevent."""
    root, _ = make_archive(tmp_path)
    point_at(monkeypatch, tmp_path, root)
    BAM.cmd_generate(["ecosim"], "2026-08-25")
    (root / "R9_test_abc1234" / "ecosim.f90.x").write_bytes(b"DIFFERENT-binary")
    assert BAM.cmd_verify(["ecosim"]) == 2


def test_M3_a_binary_disagreeing_with_its_OWN_provenance_is_caught(tmp_path, monkeypatch):
    root, _ = make_archive(tmp_path, sha_in_provenance="wrong")
    point_at(monkeypatch, tmp_path, root)
    entries, problems = BAM.scan("ecosim")
    assert any("its OWN PROVENANCE" in p for p in problems), problems


def test_M4_an_unrecorded_archive_WARNS_but_does_not_error(tmp_path, monkeypatch):
    """A newly archived build is normal; it should prompt a regenerate, not fail a gate."""
    root, _ = make_archive(tmp_path)
    point_at(monkeypatch, tmp_path, root)
    BAM.cmd_generate(["ecosim"], "2026-08-25")
    make_archive(tmp_path, label="R9_second_def5678", content=b"another")
    assert BAM.cmd_verify(["ecosim"]) == 1


def test_M5_a_dir_with_no_binary_is_reported_not_crashed(tmp_path, monkeypatch):
    root, _ = make_archive(tmp_path)
    (root / "not_an_archive").mkdir()
    point_at(monkeypatch, tmp_path, root)
    entries, problems = BAM.scan("ecosim")
    assert len(entries) == 1
    assert any("not a binary archive" in p for p in problems), problems


def test_a_missing_PROVENANCE_is_reported(tmp_path, monkeypatch):
    root, _ = make_archive(tmp_path, sha_in_provenance="absent")
    point_at(monkeypatch, tmp_path, root)
    _, problems = BAM.scan("ecosim")
    assert any("no SHA256" in p or "missing" in p for p in problems), problems


# ------------------------------------------------------------------ verify: the pass

def test_an_intact_archive_verifies_clean(tmp_path, monkeypatch):
    root, _ = make_archive(tmp_path)
    point_at(monkeypatch, tmp_path, root)
    BAM.cmd_generate(["ecosim"], "2026-08-25")
    assert BAM.cmd_verify(["ecosim"]) == 0


def test_the_manifest_is_small(tmp_path, monkeypatch):
    """The whole point: a few KB of text stands in for hundreds of MB of binaries. If this ever
    grows large, someone has started storing the wrong thing."""
    root, _ = make_archive(tmp_path)
    man = point_at(monkeypatch, tmp_path, root)
    BAM.cmd_generate(["ecosim"], "2026-08-25")
    assert man.stat().st_size < 8192


# ------------------------------------------------------------------ the live tree

def test_the_real_manifest_verifies():
    """The six real EcoSIM archives are present and unaltered. Skips where CFS is unavailable, so
    this never fails for being off the HPC filesystem."""
    if not Path(BAM.ARCHIVES["ecosim"]["archive_root"]).is_dir():
        pytest.skip("EcoSIM archive root not present on this machine")
    assert BAM.cmd_verify(["ecosim"]) == 0


# ---------------------------------------------------------------------------------- M7 ----------
# The round ledger's provenance claim must RESOLVE against the manifest. Before this rule, the
# `sha256_prefix` in calibration_rounds.yaml was an assertion nobody verified -- the cross-check
# reported in v2.305 was done once, by hand, and nothing re-ran it.
#
# The first implementation walked `rounds` and matched NOTHING, because `round_binaries` hangs off
# `model_change_ledger`. It reported a clean pass while verifying zero claims. Both tests below
# therefore assert an ERROR is RAISED, and `test_M7_the_happy_path_actually_checks_something`
# asserts the check is not vacuous.

LEDGER = """
model: ecosim
model_change_ledger:
  round_binaries:
    3:
      archived_build: build_archive/{label}/ecosim.f90.x
      sha256_prefix: {prefix}
"""


def _ledger(man, label, prefix):
    (man.parent / "calibration_rounds.yaml").write_text(LEDGER.format(label=label, prefix=prefix))


def test_M7_a_wrong_sha_prefix_in_the_ledger_is_an_ERROR(tmp_path, monkeypatch):
    root, real = make_archive(tmp_path)
    man = point_at(monkeypatch, tmp_path, root)
    BAM.cmd_generate(["ecosim"], None)
    _ledger(man, "R9_test_abc1234", "deadbeef")
    assert BAM.cmd_verify(["ecosim"]) == 2


def test_M7_a_label_the_manifest_lacks_is_an_ERROR(tmp_path, monkeypatch):
    root, real = make_archive(tmp_path)
    man = point_at(monkeypatch, tmp_path, root)
    BAM.cmd_generate(["ecosim"], None)
    _ledger(man, "R9_ghost_00000000", "abcdef01")
    assert BAM.cmd_verify(["ecosim"]) == 2


def test_M7_the_happy_path_actually_checks_something(tmp_path, monkeypatch):
    """CONTROL: a CORRECT ledger passes, and the two tests above therefore mean something.

    Without this, an M7 that silently matched no rounds would pass all three.
    """
    import json
    root, real = make_archive(tmp_path)
    man = point_at(monkeypatch, tmp_path, root)
    BAM.cmd_generate(["ecosim"], None)
    sha = json.loads(man.read_text())["archives"][0]["sha256"]
    _ledger(man, "R9_test_abc1234", sha[:8])
    assert BAM.cmd_verify(["ecosim"]) == 0
    # and the same ledger with one character changed must FAIL, which is what makes it a control
    _ledger(man, "R9_test_abc1234", ("0" if sha[0] != "0" else "1") + sha[1:8])
    assert BAM.cmd_verify(["ecosim"]) == 2


# ------------------------------------------------------------------ runtime switches
# A commit and a checksum say what is IN a binary and nothing about what must be SET to use it.
# That gap is not hypothetical: EcoSIM's guard_floor_dying_stand shipped default-off, reached no
# case template, and was therefore OFF for EcoSIM_TeRaCON R1, which lost 8 of its first 364 cases
# to an abort the binary already knew how to suppress.

def test_runtime_switches_are_carried_from_provenance(tmp_path, monkeypatch):
    import json
    root, _ = make_archive(tmp_path)
    prov = root / "R9_test_abc1234" / "PROVENANCE.txt"
    prov.write_text(prov.read_text()
                    + "Runtime switches : guard_floor_dying_stand=.true. RECOMMENDED\n")
    man = point_at(monkeypatch, tmp_path, root)
    assert BAM.cmd_generate(["ecosim"], "2026-09-04") == 0
    entry = json.loads(man.read_text())["archives"][0]
    assert entry["runtime_switches"] == "guard_floor_dying_stand=.true. RECOMMENDED"


def test_runtime_switches_default_to_empty_when_provenance_is_silent(tmp_path, monkeypatch):
    """CONTROL: the field must not invent a value for an archive that declares none."""
    import json
    root, _ = make_archive(tmp_path)
    man = point_at(monkeypatch, tmp_path, root)
    assert BAM.cmd_generate(["ecosim"], "2026-09-04") == 0
    assert json.loads(man.read_text())["archives"][0]["runtime_switches"] == ""


# ------------------------------------------------------------------ symlink aliases

def test_a_symlink_alias_is_not_counted_as_a_second_archive(tmp_path, monkeypatch):
    """An alias for a renamed archive is one binary under two names, not two archives.

    Counting it would publish a duplicate label, and M4 would then demand the alias be recorded --
    entrenching a name that may exist only to be retired.
    """
    import json
    root, _ = make_archive(tmp_path)
    (root / "R9_alias_abc1234").symlink_to(root / "R9_test_abc1234")
    man = point_at(monkeypatch, tmp_path, root)
    assert BAM.cmd_generate(["ecosim"], "2026-09-04") == 0
    labels = [e["label"] for e in json.loads(man.read_text())["archives"]]
    assert labels == ["R9_test_abc1234"], labels
    # and the alias must not raise an M4 "on disk but not in the manifest" warning either
    assert BAM.cmd_verify(["ecosim"]) == 0


def test_a_real_second_copy_IS_counted(tmp_path, monkeypatch):
    """CONTROL for the test above: a deliberate second COPY is a real archive and is recorded.

    This is how TeRaCONbase_forkmain_0366560a relates to R4base_forkmain_0366560a -- two real
    directories holding identical bytes, each with its own PROVENANCE.txt, both in the manifest.
    """
    import json, shutil
    root, _ = make_archive(tmp_path)
    shutil.copytree(root / "R9_test_abc1234", root / "R9_copy_abc1234")
    man = point_at(monkeypatch, tmp_path, root)
    assert BAM.cmd_generate(["ecosim"], "2026-09-04") == 0
    entries = json.loads(man.read_text())["archives"]
    labels = sorted(e["label"] for e in entries)
    assert labels == ["R9_copy_abc1234", "R9_test_abc1234"], labels
    assert entries[0]["sha256"] == entries[1]["sha256"]        # same bytes, two labels


# ------------------------------------------------------------------ multi-manifest

def test_generate_writes_EVERY_manifest_and_verify_checks_EVERY_ledger(tmp_path, monkeypatch):
    """One manifest per case whose ledger cites these binaries.

    M7 resolves a ledger against the manifest BESIDE IT, so a single shared manifest left every
    other case's provenance claims checked by nothing -- which is what happened to
    EcoSIM_TeRaCON R1 until 2026-09-04.
    """
    import json
    root, _ = make_archive(tmp_path)
    a, b = tmp_path / "caseA" / "m.json", tmp_path / "caseB" / "m.json"
    monkeypatch.setitem(BAM.ARCHIVES, "ecosim", {
        "archive_root": str(root),
        "manifests": [a, b],
        "binary_name": "ecosim.f90.x",
    })
    assert BAM.cmd_generate(["ecosim"], "2026-09-04") == 0
    assert a.is_file() and b.is_file()
    assert json.loads(a.read_text())["archives"] == json.loads(b.read_text())["archives"]

    sha = json.loads(a.read_text())["archives"][0]["sha256"]
    _ledger(a, "R9_test_abc1234", sha[:8])          # caseA correct
    _ledger(b, "R9_test_abc1234", sha[:8])          # caseB correct
    assert BAM.cmd_verify(["ecosim"]) == 0

    # A wrong claim in the SECOND case's ledger must still be caught -- the failure mode this
    # change exists to end is a case whose ledger nothing looked at.
    _ledger(b, "R9_test_abc1234", ("0" if sha[0] != "0" else "1") + sha[1:8])
    assert BAM.cmd_verify(["ecosim"]) == 2
