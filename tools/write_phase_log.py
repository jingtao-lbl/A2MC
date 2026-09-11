#!/usr/bin/env python
"""Write an offline calibration PHASE LOG and its paired artifact folder, from one payload.

THE MECHANICS ARE A2MC'S, THE CONTENT IS THE CASE'S. Every case had been hand-rolling its own
driver over `tools/phase_logger.py`: 47 tracked copies of `write_phase{N}_log.py` across two cases
on 2026-09-07, 39 of them stem copies. The per-case part of those files is the constants and the
reasoning prose, which genuinely differ. The rest is identical boilerplate, and it is where the
failures were ([[feedback_per_model_scripts_not_generic]]: A2MC's own machinery is generic, and
log-writing is A2MC's own machinery).

THREE FAILURES THIS TOOL MAKES IMPOSSIBLE, all measured on 2026-09-07 in one session:

  1. NO SITE  ->  a log written into `use_cases/TEMPLATE/`, stamped `**Site:** TEMPLATE`, inside a
     nested tree under whatever directory the script happened to run from. `create_logger()` falls
     back to TEMPLATE; this tool HARD-FAILS instead, because a log in the wrong case is worse than
     no log.
  2. AGENT MODE UNSET  ->  the log written in the ONLINE nested layout
     (`logs/<session>/phase{N}_{name}/`) while `topic_artifact_dir()` keeps the OFFLINE stem, which
     orphans the pairing. `PhaseLogger` warns and then writes anyway. This tool sets offline mode
     before constructing the logger, so the warning has nothing to warn about.
  3. STEM SPLIT  ->  the artifact folder and the log minted DIFFERENT same-day letters, because the
     descriptor was slugified to different lengths. The stem is minted ONCE here and the pairing is
     ASSERTED after the write, so a split cannot be committed rather than being caught later by
     `check_stem_pairing.py`.

USAGE

    python tools/write_phase_log.py --phase 4 --payload <path/to/payload.py> [--site-dir DIR]

The payload is a PYTHON module (not JSON: the reasoning body is a long r-string and wants to stay
one). It must define:

    TITLE      str   -- goes to BOTH the artifact dir and the log; one string, one stem
    COUNTERS   dict  -- iteration / calibration_round / experiment_count / skip_testing_count
    HANDSHAKE  dict  -- inherited_from / handed_to / next_action
    LOG        dict  -- the phase method's own kwargs, EXCLUDING title

`LOG` is passed through verbatim, so this tool never has to know a phase's kwarg names and does not
fork the contract when `PhaseLogger` gains a field. It is a thin front-end over the same API the
ONLINE agent uses, deliberately: a second way to write a log would be a second contract.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations
import argparse
import importlib.util
import os
import pathlib
import sys

METHOD = {0: "log_design", 1: "log_exploration", 2: "log_screening", 3: "log_diagnosis",
          4: "log_hypothesis", 5: "log_testing", 6: "log_refinement"}


def _load_payload(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("a2mc_phase_log_payload", path)
    if spec is None or spec.loader is None:
        raise SystemExit("ERROR: cannot import payload %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", type=int, required=True, choices=sorted(METHOD))
    ap.add_argument("--payload", required=True, help="python module defining TITLE/COUNTERS/HANDSHAKE/LOG")
    ap.add_argument("--site-dir", default=None,
                    help="the use_cases/<Model>_<Case> dir; default $A2MC_USE_CASE_DIR")
    ap.add_argument("--method", default=None,
                    help="override the phase's log_* method (e.g. log_experiment_design for phase 4)")
    a = ap.parse_args()

    repo = next(p for p in pathlib.Path(__file__).resolve().parents
                if (p / "tools" / "phase_logger.py").is_file())
    sys.path.insert(0, str(repo))

    # (1) SITE -- resolve or refuse. Never fall back to TEMPLATE: a log written into the template
    # case is not a smaller version of the right log, it is a wrong one, and it is committed before
    # anyone notices because every checker passes on it.
    site = a.site_dir or os.environ.get("A2MC_USE_CASE_DIR") or ""
    if not site.strip():
        raise SystemExit(
            "ERROR: no site. Pass --site-dir use_cases/<Model>_<Case>, or export A2MC_USE_CASE_DIR.\n"
            "  Refusing to let PhaseLogger fall back to use_cases/TEMPLATE, which writes a log\n"
            "  stamped '**Site:** TEMPLATE' that passes every conformance check.")
    site_p = pathlib.Path(site)
    if not site_p.is_absolute():
        site_p = repo / site_p
    if not site_p.is_dir():
        raise SystemExit("ERROR: site dir does not exist: %s" % site_p)
    if site_p.name == "TEMPLATE":
        raise SystemExit("ERROR: refusing to write a calibration log into use_cases/TEMPLATE")

    # (2) AGENT MODE -- set before the logger is constructed, so the offline flat-stem layout is
    # chosen rather than warned about after the fact.
    os.environ["A2MC_AGENT_MODE"] = "offline"

    pl = _load_payload(pathlib.Path(a.payload).resolve())
    for name in ("TITLE", "COUNTERS", "HANDSHAKE", "LOG"):
        if not hasattr(pl, name):
            raise SystemExit("ERROR: payload defines no %s" % name)
    title = pl.TITLE
    if not isinstance(title, str) or not title.strip():
        raise SystemExit("ERROR: payload TITLE must be a non-empty string")

    from tools.phase_logger import create_logger
    lg = create_logger(site_dir=str(site_p))
    lg.set_iteration_context(**pl.COUNTERS)
    lg.set_phase_handshake(**pl.HANDSHAKE)

    # (3) ONE STRING, ONE STEM. The artifact dir and the log both derive from `title` here, and the
    # pairing is asserted below rather than left to a later checker.
    stem = lg.topic_stem(a.phase, title)
    art = lg.topic_artifact_dir(a.phase, title)

    method = a.method or METHOD[a.phase]
    log_path = pathlib.Path(getattr(lg, method)(title=title, **pl.LOG))

    if log_path.stem != art.name:
        raise SystemExit(
            "ERROR: STEM SPLIT -- the log and its artifact folder do not pair.\n"
            "  log    : %s\n  folder : %s\n"
            "  Both derive from TITLE, so this means the descriptor slugified differently or a\n"
            "  same-day letter was already taken. Fix the title or rename the folder, then re-run."
            % (log_path.name, art.name))

    print("stem   :", stem)
    print("log    :", log_path)
    print("folder :", art)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
