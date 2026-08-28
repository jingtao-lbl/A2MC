"""ATS adapter smoke test — run from repo root with Python 3.10:

    python models/ats/tests/test_smoke.py

Exercises registration, the XML parameter parser (units + region multiplicity), the
observation output parser, the write round-trip (with fail-loud), and version-tier
classification against the committed real-deck fixtures. Exits nonzero on any failure.

Not a pytest suite (kept dependency-free); the assertions are plain and self-reporting.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root on path when run directly.
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import models.ats  # noqa: E402  (triggers registration)
from models import registry  # noqa: E402
from models.ats.parameter_parser import ATSParameterParser  # noqa: E402
from models.ats.output_parser import ATSOutputParser  # noqa: E402
from models.ats.version import ATSVersion, ATSBumpTierClassifier, Tier  # noqa: E402

FIX = _REPO / "models/ats/tests/fixtures"
DECKS = ["priestley_taylor.xml", "oakharbor_column.xml", "oakharbor_transect.xml"]


def main() -> int:
    fails = []

    def check(cond, msg):
        print(("  ok  " if cond else " FAIL ") + msg)
        if not cond:
            fails.append(msg)

    # Registration
    check("ats" in registry.list_models(), "ats registered in model registry")
    check("ats-42b0e940" in registry.list_datasets("ats")["ats"], "ats-42b0e940 dataset registered")
    be = registry.get_model("ats")
    check(be.spec.name == "ats", "backend spec name == 'ats'")

    # Parameter parser
    pp = ATSParameterParser()
    for deck in DECKS:
        recs = pp.parse(FIX / deck)
        cal = pp.calibration_parameters(FIX / deck)
        check(len(recs) > 30, f"{deck}: parsed >30 numeric params ({len(recs)})")
        check(len(cal) > 5, f"{deck}: found >5 calibratable knobs ({len(cal)})")
        cats = {v["category"] for v in cal.values()}
        check("water_retention" in cats, f"{deck}: water_retention knobs present")
        # units extracted from [...] at least once
        check(any(v["units"] for v in cal.values()), f"{deck}: at least one knob has units")

    # Region multiplicity: WRM alpha keyed under a region container
    recs = pp.parse(FIX / "oakharbor_column.xml")
    wrm = [v for v in recs.values() if "van Genuchten alpha" in v["leaf"]]
    check(len(wrm) >= 1 and wrm[0]["region"], "WRM alpha carries a region label (multiplicity)")

    # Output parser: observations block
    outs = ATSOutputParser().parse(FIX / "oakharbor_transect.xml")
    check(len(outs) >= 5, f"transect observations: >=5 target variables ({len(outs)})")
    check(any(v["output_filename"] == "water_balance.dat" for v in outs.values()),
          "observations resolve to water_balance.dat")

    # Write round-trip + fail-loud
    recs = pp.parse(FIX / "priestley_taylor.xml")
    perm = [k for k in recs if k.endswith("evaluators/permeability/value")]
    mods = {perm[0]: recs[perm[0]]["default"] * 2}
    out = FIX / "_roundtrip_out.xml"
    be.write_parameter_file(FIX / "priestley_taylor.xml", mods, out)
    re2 = pp.parse(out)
    check(abs(re2[perm[0]]["default"] - mods[perm[0]]) < 1e-30, "write round-trip: value doubled")
    out.unlink(missing_ok=True)
    raised = False
    try:
        be.write_parameter_file(FIX / "priestley_taylor.xml", {"no/such/addr": 1.0}, out)
    except ValueError:
        raised = True
    out.unlink(missing_ok=True)
    check(raised, "write fails loud on unknown address")

    # Version tiers
    v = ATSVersion.from_describe("ats-1.7-dev-22-g42b0e940", commit_sha="42b0e9401234")
    v2 = ATSVersion.from_describe("ats-1.7.2-0-gdeadbeef", commit_sha="deadbeef9999")
    v3 = ATSVersion.from_describe("ats-2.0.0-0-gfeed0000", commit_sha="feed00001111")
    cls = ATSBumpTierClassifier()
    check(v.label == "ats-42b0e940", "version label == ats-42b0e940")
    check(cls.classify(v, v) == Tier.T1, "same commit -> T1")
    check(cls.classify(v, v2) == Tier.T2, "same epoch -> T2")
    check(cls.classify(v, v3) == Tier.T3, "diff major -> T3")

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print("ALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
