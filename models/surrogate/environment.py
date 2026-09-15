"""What a saved surrogate was BUILT with, and whether the loader still has it.

`Provenance` answers "what is this artifact valid against" in terms the CALLER supplies: the model
commit, the parameter list, the scoring convention. This module answers a different question that
nobody supplies and everybody assumes: **which library versions produced these weights, and are
they the ones about to read them back.**

The two are deliberately separate files rather than more `Provenance` fields. Provenance is
identity, hand-stamped and semantically meaningful (`mismatches()` treats an empty field as
unknown, and `unstamped_fields()` is a report on the human who filled it in). The environment is
mechanical, captured automatically, and true of the machine rather than of the science. Folding it
into `Provenance` would have made every pre-existing artifact report five more "unstamped" fields
that no human was ever going to fill in, which is how a warning becomes noise.

WHAT IS RECORDED, AND WHY IT IS NOT SIMPLY "EVERY INSTALLED PACKAGE". Only libraries that were
actually IMPORTED when the artifact was saved, intersected with the short list below. A pip freeze
records what the machine happened to have; this records what the artifact was built with. The
difference matters on load: a scikit-learn S1 artifact saved on a machine that also has torch must
not demand torch from a machine that does not, and it will not, because torch was never imported
while fitting it.

SEVERITY IS TWO-LEVEL, AND THE LINE IS DRAWN AT THE MAJOR VERSION. A joblib pickle of a
scikit-learn estimator is not guaranteed to survive a major bump; it usually survives a minor one
with a warning from sklearn itself. So a MAJOR difference, or a library that has gone missing
entirely, is a refusal under `strict`; anything else is a warning. That is a judgement, and it is
stated here rather than buried, because the alternative -- refusing on any difference -- would make
the check unusable the first time anyone runs `pip install -U` and would train people to pass
`strict=False` permanently.

Author: Jing Tao with Claude on Perlmutter
"""

from __future__ import annotations

import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

#: The file a saved artifact carries beside `spec.json`.
ENVIRONMENT_FILE = "environment.json"

#: Libraries whose version can change what a reloaded artifact PREDICTS, by import name.
#: Keyed by import name because that is what `sys.modules` holds; the distribution name is only
#: needed for a human-readable message, and `scikit-learn` is the one place they differ.
STAMPED_LIBRARIES = {
    "numpy": "numpy",
    "scipy": "scipy",
    "sklearn": "scikit-learn",
    "joblib": "joblib",
    "torch": "torch",
}


@dataclass(frozen=True)
class EnvMismatch:
    """One library that differs between the saving machine and this one."""

    library: str
    recorded: Optional[str]      # None when the library was not recorded
    current: Optional[str]       # None when it is not importable here
    severity: str                # "major" | "minor"

    def __str__(self) -> str:
        if self.current is None:
            return (f"{self.library}: recorded {self.recorded}, NOT INSTALLED here "
                    f"({self.severity})")
        return (f"{self.library}: recorded {self.recorded}, current {self.current} "
                f"({self.severity})")


def _version_of(import_name: str) -> Optional[str]:
    mod = sys.modules.get(import_name)
    if mod is None:
        return None
    return str(getattr(mod, "__version__", "")) or None


def _installed_version(import_name: str) -> Optional[str]:
    """Version of an installed library, importing it if necessary.

    Used on the LOAD side, where the library may not have been imported yet: checking
    `sys.modules` alone would report every recorded library as missing and turn the check into
    noise on its first run.
    """
    v = _version_of(import_name)
    if v is not None:
        return v
    try:
        mod = __import__(import_name)
    except Exception:
        return None
    return str(getattr(mod, "__version__", "")) or None


def _major(version: Optional[str]) -> Optional[str]:
    """Leading numeric component, e.g. '2.10.0+cu128' -> '2'. None when unparseable."""
    if not version:
        return None
    head = version.split("+")[0].split(".")[0].strip()
    return head if head.isdigit() else None


def capture_environment() -> Dict[str, Any]:
    """Record the interpreter and the libraries currently IMPORTED, for the artifact being saved.

    Called from `SurrogateModel.save`, so "currently imported" means "imported by the code that
    fitted this artifact", which is the property worth recording.
    """
    libs = {}
    for import_name in STAMPED_LIBRARIES:
        v = _version_of(import_name)
        if v is not None:
            libs[import_name] = v
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "libraries": libs,
    }


def write_environment(directory: Path) -> Path:
    path = Path(directory) / ENVIRONMENT_FILE
    path.write_text(json.dumps(capture_environment(), indent=2))
    return path


def read_environment(directory: Path) -> Optional[Dict[str, Any]]:
    """The recorded environment, or None for an artifact saved before this existed."""
    path = Path(directory) / ENVIRONMENT_FILE
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def check_environment(recorded: Optional[Mapping[str, Any]]) -> List[EnvMismatch]:
    """Differences between a recorded environment and this interpreter, worst first.

    An empty list means every recorded library is present at the same version. ``recorded=None``
    also returns an empty list: an artifact with no stamp is UNPROTECTED, not verified, and saying
    so is the caller's job (it has the `None` and can warn about it) rather than this function's,
    which would otherwise have to invent a mismatch that did not happen.
    """
    if not recorded:
        return []
    out: List[EnvMismatch] = []

    rec_py = recorded.get("python")
    cur_py = sys.version.split()[0]
    if rec_py and rec_py != cur_py:
        # A python MAJOR bump breaks pickles; a minor one is a warning. 3.11 -> 3.12 is minor here.
        sev = "major" if _major(rec_py) != _major(cur_py) else "minor"
        out.append(EnvMismatch("python", rec_py, cur_py, sev))

    for import_name, rec_v in (recorded.get("libraries") or {}).items():
        cur_v = _installed_version(import_name)
        if cur_v is None:
            out.append(EnvMismatch(STAMPED_LIBRARIES.get(import_name, import_name),
                                   rec_v, None, "major"))
            continue
        if cur_v == rec_v:
            continue
        sev = "major" if _major(rec_v) != _major(cur_v) else "minor"
        out.append(EnvMismatch(STAMPED_LIBRARIES.get(import_name, import_name),
                               rec_v, cur_v, sev))

    out.sort(key=lambda m: (m.severity != "major", m.library))
    return out


def enforce_environment(directory: Path, strict: bool = True) -> List[EnvMismatch]:
    """Read, compare, and refuse or warn. Returns the mismatches for a caller that wants them.

    Refuses under ``strict`` on a MAJOR mismatch only. A missing stamp warns, because every
    artifact built before this module existed has none and hard-failing them would make the
    feature unadoptable on exactly the artifacts that most need auditing.
    """
    import warnings

    directory = Path(directory)
    recorded = read_environment(directory)
    if recorded is None:
        warnings.warn(
            f"surrogate at {directory} carries no {ENVIRONMENT_FILE}; the library versions that "
            f"produced it are unknown, so a silent change in them cannot be detected. The "
            f"artifact is unprotected against that, not verified against it.",
            RuntimeWarning)
        return []

    bad = check_environment(recorded)
    major = [m for m in bad if m.severity == "major"]
    if major:
        detail = "; ".join(str(m) for m in major)
        msg = (f"environment mismatch in {directory}: {detail}. A major version change can alter "
               f"what a reloaded artifact predicts, or prevent it loading at all. Rebuild the "
               f"artifact under the current environment, or load with strict=False having "
               f"decided the change is safe.")
        if strict:
            raise ValueError(msg)
        warnings.warn(msg, RuntimeWarning)
    minor = [m for m in bad if m.severity == "minor"]
    if minor:
        warnings.warn(
            f"environment drift in {directory}: " + "; ".join(str(m) for m in minor)
            + ". Minor versions differ from the ones this artifact was built with.",
            RuntimeWarning)
    return bad
