"""pytest config — put the repo root on sys.path so tests can import tools/, memory/."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pytest_configure(config):
    """Create the --basetemp parent dir before any tmp_path fixture needs it.

    pytest.ini pins --basetemp=tmp/pytest (repo-local, gitignored — NERSC forbids
    writes outside home). pytest mkdir()s an explicit --basetemp WITHOUT parents=True,
    so in a fresh clone, where the gitignored tmp/ does not exist, every tmp_path test
    errors at setup with FileNotFoundError.
    """
    basetemp = config.option.basetemp
    if basetemp:
        parent = os.path.dirname(str(basetemp))
        if parent:
            os.makedirs(parent, exist_ok=True)
