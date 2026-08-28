"""PFLOTRAN backend.

Follows the EcoSIM precedent: parsing, output extraction and calibration
parameter writing (the 16-knob deck surface) are implemented; case creation
and HPC submission are still deferred (dev log `20260807c` §4 — deck writing
was the blocker; case-directory assembly is the next one). Deferred methods
raise ``NotImplementedError`` with the reason rather than returning a
plausible wrong answer.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..base import ModelBackend
from .output_parser import PFLOTRANOutputParser
from .parameter_parser import PFLOTRANParameter, PFLOTRANParameterParser
from .spec import PFLOTRAN_SPEC

# PFLOTRAN's own failure exit code (src/pflotran/pflotran_constants.F90:63).
# Returned via `call exit(iflag)` after `Simulation failed.  Exiting!`.
PFLOTRAN_EXIT_FAILURE = 88

# The mass-balance tape's time column. Always present (it is written first,
# `output_observation.F90`), and every PFLOTRAN target window is expressed in its
# units — see WINDOWS ARE HOURS below — so extraction always returns it.
PFLOTRAN_TIME_COLUMN = "Time [h]"

# Water density [kg/m^3] used to convert the coupler's water MASS rate [kg/h] to
# a VOLUME rate [L/h] when forming a concentration. The deck's EOS WATER block
# leaves DENSITY commented out (pflotran.in:56) and sets only VISCOSITY, so
# PFLOTRAN uses its internal EOS; 997.16 is the value the deck's own ROCK_DENSITY
# comment implies and is within 0.2 % of the EOS value at 25 C. That is far below
# the 30-60 % target uncertainties in miniLEO's targets.yaml, but it IS an
# assumption, so it is named here and overridable per target (`water_density`)
# rather than buried in the arithmetic.
PFLOTRAN_WATER_DENSITY = 997.16

# The east-face outflow plan area [m^2] used to convert a mass RATE [kg/h] to a
# depth RATE [mm/h] for the absolute hydrograph reduce (``outflow_flux``, not the
# ratio-based ``outflow_concentration``, which cancels this constant exactly and
# so never depends on it). 2.0 x 0.5 is the miniLEO mesh footprint (mesh.ugi x/y
# extent), confirmed 2026-08-07 (targets.yaml header) as a physical dimension,
# not a fitted constant. Overridable per target (`plan_area_m2`).
PFLOTRAN_PLAN_AREA_M2 = 2.0 * 0.5

# Offset [h] between the MODEL clock (t=0 at the start of this deck's spin-up)
# and the OBSERVATION clock (t=0 at the start of the physical experiment) that
# every miniLEO measured series is timestamped against — see targets.yaml's
# "OBSERVATION CLOCK IS OFFSET" block. Overridable per target
# (`experiment_start_h`) for a different site/deck sharing this backend.
PFLOTRAN_EXPERIMENT_START_H = 806.0

# Repo root, for resolving a target's `observed_series_file` (see
# `_reduce_outflow_flux`) when given as a repo-relative path.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class PFLOTRANBackend(ModelBackend):
    """Executable interface for PFLOTRAN. Parsing implemented; execution deferred."""

    spec = PFLOTRAN_SPEC

    # ---- parsing (implemented) -------------------------------------------
    def parse_parameters(self, param_file: Path) -> Dict[str, Any]:
        """Parse an input DECK. PFLOTRAN has no parameter file in the FATES sense."""
        return PFLOTRANParameterParser().parse(param_file)

    def parse_outputs(self, output_file: Path) -> Dict[str, Any]:
        """Inventory a `*-mas.dat` header. There is no output CDL for this model."""
        return PFLOTRANOutputParser().parse(output_file)

    # ---- output extraction (implemented) ---------------------------------
    def extract_history_variables(self, case_path: Path, variables: List[str],
                                  time_range: Optional[tuple] = None,
                                  tape: str = "h0") -> Any:
        """Read named `*-mas.dat` columns from a completed case.

        ``variables`` are full column headers, e.g. ``"east Water Mass [kg/h]"``.
        Full headers are required because the cumulative and rate columns share a
        variable STEM ("east Water Mass") and differ only in units
        (`output_observation.F90:2617-2622`). The full headers themselves are
        distinct — all 332 are unique in the miniLEO file — so passing them is
        unambiguous; passing a stem would not be. Returns ``{column: [values]}``.

        ``Time [h]`` is ALWAYS included whether or not it was requested: every
        PFLOTRAN target window is in hours, so any reduce over this tape needs the
        time column to resolve one. Callers that did not ask for it can ignore it.

        ``tape`` is IGNORED: PFLOTRAN writes a single mass-balance output, no multi-tape
        concept (accepted only for signature parity with the model-agnostic caller).
        """
        case_path = Path(case_path)
        mas = sorted(case_path.glob("*-mas.dat"))
        if not mas:
            raise FileNotFoundError(f"no *-mas.dat under {case_path}")
        parser = PFLOTRANOutputParser()
        inventory = parser.parse(mas[0])
        missing = [v for v in variables if v not in inventory]
        if missing:
            raise KeyError(f"columns not in {mas[0].name}: {missing}")
        wanted = list(variables)
        if PFLOTRAN_TIME_COLUMN in inventory and PFLOTRAN_TIME_COLUMN not in wanted:
            wanted.append(PFLOTRAN_TIME_COLUMN)
        series = parser.read_series(mas[0], [inventory[v] for v in wanted])
        if time_range:
            lo, hi = time_range
            series = {k: v[lo:hi] for k, v in series.items()}
        return series

    # ---- case status (implemented) ---------------------------------------
    def check_case_status(self, case_path: Path) -> str:
        """'COMPLETED' | 'FAILED' | 'RUNNING' | 'PENDING'.

        Keys on PFLOTRAN's own signals rather than on cut counts. A run reporting
        many timestep cuts has NOT necessarily failed: ``MAX_TS_CUTS`` is a
        PER-TIMESTEP CONSECUTIVE budget reset at every step
        (`timestepper_SNES.F90:371`), so the lifetime `cuts` figure in the run
        summary is unrelated to the limit. The miniLEO run completed successfully
        with 168 lifetime cuts against a limit of 20 — reading that as failure is
        the mistake this method exists to avoid.
        """
        case_path = Path(case_path)
        out = sorted(case_path.glob("*.out"))
        if not out:
            return "PENDING"
        text = out[0].read_text(errors="replace")
        if "Simulation failed" in text or "Stopping: Time step cut criteria exceeded" in text:
            return "FAILED"
        if "Wall Clock Time:" in text:
            return "COMPLETED"
        return "RUNNING"

    # ---- target reduction (implemented) ----------------------------------
    #
    # WINDOWS ARE HOURS, NOT ROW INDICES — the one thing to know here.
    # `use_cases/PFLOTRAN_miniLEO/validation/targets.yaml` writes
    # ``window: [0, 768]  # hours``, while the generic
    # ``tools.model_evaluate_case.reduce_target`` treats ``window`` as 0-based ROW
    # indices (EcoSIM/FATES tapes are one row per output interval). On the miniLEO
    # tape — 3360 rows at a uniform 0.5 h step, 0.5-1680 h — the index reading of
    # [0, 768] selects 0.5-384.5 h: HALF the intended window, and a plausible
    # number rather than an error. Every reduce below resolves the window against
    # the tape's own ``Time [h]`` column, and ``select_group_series`` refuses the
    # generic index path outright rather than let the two readings coexist.
    MODEL_REDUCES = frozenset({"outflow_concentration", "outflow_flux"})

    def select_group_series(self, data, target):
        """Return the column as-is — and refuse an ambiguous generic window.

        PFLOTRAN's mass-balance columns are ALREADY reduced over their region or
        coupler by the writer, so there is no grouping-axis slot to index: the
        target's ``region``/``pft`` field names the coupler that is baked into the
        column header (``"east Na+ [mol/h]"``), not a column offset.

        The guard: a target that carries a ``window`` but not one of this model's
        derived reduces would be sliced by the generic layer as row indices, which
        for this model silently means a different time span (see WINDOWS ARE HOURS
        above). That is refused here, where the target spec is still in hand.
        """
        import numpy as np
        how = target.get("reduce", "mean")
        if "window" in target and how not in self.MODEL_REDUCES:
            raise ValueError(
                f"PFLOTRAN target {target.get('name', target.get('variable'))!r}: "
                f"reduce={how!r} with a window would be sliced by the generic layer "
                f"as ROW INDICES, but PFLOTRAN windows are in HOURS — the two "
                f"readings differ silently. Use a derived reduce "
                f"({sorted(self.MODEL_REDUCES)}), or convert the window to row "
                f"indices explicitly against the tape's 'Time [h]' column.")
        arr = np.asarray(data)
        return arr if arr.ndim == 1 else arr.reshape(arr.shape[0], -1)[:, 0]

    def reduce_derived(self, case_or_extracted: Dict[str, Any],
                       target: Dict[str, Any], how: str) -> float:
        """Derived (multi-column, or full-series) target reductions. See ``MODEL_REDUCES``.

        ``outflow_concentration`` — the time-mean concentration of a solute in the
        outflow, formed as a RATIO of two columns written at the SAME coupler:

            C_X = (X [mol/h]) / (Water Mass [kg/h] / rho * 1000)   [mol/L]

        The ratio is what makes these targets scorable without depending on the
        plan area at all: both columns carry whatever area the writer used, and it
        divides out exactly. (The east-face plan area itself is NOT unresolved —
        confirmed 1.0 m^2 from mesh.ugi geometry, targets.yaml header, 2026-08-07 —
        but this reduce never needed that fact to be scorable.)

        ``outflow_flux`` — see ``_reduce_outflow_flux``: the absolute hydrograph,
        which DOES use the plan area (``PFLOTRAN_PLAN_AREA_M2``), scored as a
        full-series RMSRE rather than a single ratio.
        """
        if how == "outflow_flux":
            return self._reduce_outflow_flux(case_or_extracted, target)
        if how != "outflow_concentration":
            return super().reduce_derived(case_or_extracted, target, how)

        extracted = case_or_extracted
        num_col = target["variable"]
        den_col = target.get("denominator")
        if not den_col:
            raise ValueError(
                f"target {target.get('name', num_col)!r}: reduce "
                f"'outflow_concentration' is a ratio and requires a 'denominator' "
                f"column (the water-mass rate at the same coupler)")
        for col in (num_col, den_col, PFLOTRAN_TIME_COLUMN):
            if col not in extracted:
                raise KeyError(
                    f"target {target.get('name', num_col)!r}: column {col!r} not in "
                    f"extracted history {sorted(extracted)}")

        rho = float(target.get("water_density", PFLOTRAN_WATER_DENSITY))
        time = list(extracted[PFLOTRAN_TIME_COLUMN])
        numer = list(extracted[num_col])
        water = list(extracted[den_col])

        lo, hi = target.get("window", (time[0], time[-1]))       # HOURS, inclusive
        self._assert_window_covered(target, time, lo, hi)

        conc = []
        for t, x, w in zip(time, numer, water):
            if t < lo or t > hi:
                continue
            if w == 0:
                continue          # no outflow -> concentration is undefined, not 0
            conc.append(x / (w / rho * 1000.0))
        if not conc:
            raise ValueError(
                f"target {target.get('name', num_col)!r}: window {lo}-{hi} h selects "
                f"no time steps with outflow (tape spans {time[0]}-{time[-1]} h). "
                f"NOTE PFLOTRAN windows are HOURS, not row indices.")
        return sum(conc) / len(conc)

    @staticmethod
    def _assert_window_covered(target: Dict[str, Any], time, lo, hi) -> None:
        """Refuse to score a target whose window runs past the end of the tape.

        THE FAILURE THIS EXISTS FOR. Both reduces below already raise when a window selects NO
        rows -- that is the obvious error and it was covered. The dangerous case is PARTIAL
        coverage: a tape that ends mid-window yields a perfectly ordinary-looking number computed
        from the rows that happen to exist. A case killed at hour 905 scored its `[806, 1612]`
        hydrograph target and returned 0.4210 with no warning (measured 2026-08-27 on
        `miniLEO_case6`, mid-run at the time). At ensemble scale some cases WILL die partway, and
        every one of them would contribute a plausible, silently wrong row to the Y matrix -- the
        worst kind of bad data, because nothing downstream can tell it from a real result.

        `pflotran-run-workflow` Step 5 already warns that "a scheduler-COMPLETED case is not a
        usable case" and that a truncated tape's surviving tail is biased. That warning lived only
        in prose; this is the enforcement.

        WHAT MAKES IT FAIL (named first, per [[feedback_a_check_that_cannot_fail]]): a tape whose
        last timestamp is below the window's upper bound. Verified in both directions -- a complete
        1680 h tape passes every miniLEO target, and a 905 h tape raises on the hydrograph while
        still passing the cycle-A chemistry window, which is the correct discrimination rather than
        a blanket rejection.
        """
        t_end = max(time)
        # ONLY partial coverage. If the window starts BEYOND the tape entirely (lo > t_end) this is
        # not a truncated run at all -- it is almost always the row-indices-vs-hours trap, and the
        # callers' own "selects no time steps" error names that trap specifically. Firing here
        # first would replace a precise diagnosis with a vaguer one; two existing tests assert that
        # message and caught exactly this when the guard was first written too broadly.
        if lo <= t_end < hi:
            raise ValueError(
                f"target {target.get('name', target.get('variable'))!r}: the tape ENDS AT "
                f"{t_end:g} h but the scored window is {lo}-{hi} h -- it covers only "
                f"{100.0 * max(0.0, t_end - lo) / (hi - lo):.1f}% of it. This case is truncated "
                f"(still running, or it died partway). Scoring it would return a plausible number "
                f"from a biased tail. Re-score once the run completes; if it FAILED, exclude it "
                f"rather than letting a partial tape into the Y matrix.")

    def _reduce_outflow_flux(self, extracted: Dict[str, Any], target: Dict[str, Any]) -> float:
        """``outflow_flux`` — full-series RMSRE of simulated vs. measured hydrograph.

        Unlike ``outflow_concentration`` (a ratio that collapses to one time-mean
        number), this scores the whole hydrograph SHAPE: simulated outflow [mm/h] —

            outflow[mm/h] = -(Water Mass [kg/h]) / rho / plan_area_m2 * 1000

        — is interpolated onto every timestamp the measured series actually HAS a
        row for. A sparse, irregularly-timed series is expected: miniLEO's
        tipping-bucket gauge has NO rows for the day-3-to-11 sensor-failure window
        (confirmed against ``measured_hydrograph.txt`` and the experiment PDF,
        20260813), so that gap contributes nothing to the score rather than
        needing an explicit exclusion — there is simply no measured row to
        interpolate onto during it.

        Requires ``target["observed_series_file"]``: a path (repo-relative or
        absolute) to a two-column ``[day_since_experiment_start, mm/h]`` text
        file — NOT baked into this backend, since a different PFLOTRAN case would
        have a different measured series (mirrors ``denominator`` being a
        target-level field, not a backend constant).

        METRIC IS NRMSE, NOT PER-POINT RELATIVE ERROR — checked against the real
        data before picking this (20260813). miniLEO's tipping-bucket gauge
        genuinely reads exact 0.0 mm/h at low flow between pulses (confirmed: the
        same quantum value, e.g. 0.092624 mm/h, recurs identically across several
        rows, alternating with 0.0 — the signature of "one tip this bin" vs "no
        tip this bin," not sensor failure). A per-point ``(sim-obs)/obs`` blows up
        at those real zeros regardless of the floor chosen (a floor of 1e-3 gave
        RMSRE > 19 on the V0 reference run, dominated by 8 of 874 points). NRMSE
        normalizes ONCE, by the observed series' range (``CostFunction``,
        ``NormalizationMethod.RANGE``), so a handful of true zero-flow points are
        just ordinary data, not a division hazard.

        SENTINEL CONVENTION for ``observed`` — this is what lets ``outflow_flux``
        plug into the SAME shared ``relative_error`` outer aggregation every other
        PFLOTRAN target uses (``evaluate_pflotran_case`` applies one ``method=``
        to every target in one call), with no change to
        ``tools/cost_functions.py`` or that call's signature:
        ``CostFunction._relative_error`` raises on ``observed == 0``, so this
        target declares ``observed: 1.0`` and this method returns
        ``1.0 + nrmse`` — recovering the NRMSE exactly, since
        ``|sim-obs|/obs == |(1+nrmse)-1|/1 == nrmse``. Document this ON the
        target in targets.yaml: unlike every other target, ``observed: 1.0``
        here is NOT a physical flow value.
        """
        import numpy as np

        from tools.cost_functions import CostFunction, NormalizationMethod, ObservationType

        num_col = target["variable"]
        series_file = target.get("observed_series_file")
        if not series_file:
            raise ValueError(
                f"target {target.get('name', num_col)!r}: reduce 'outflow_flux' "
                f"requires 'observed_series_file' (a path to a two-column "
                f"[day_since_experiment_start, mm/h] measured series)")
        series_path = Path(series_file)
        if not series_path.is_absolute():
            series_path = _REPO_ROOT / series_path
        if not series_path.is_file():
            raise FileNotFoundError(
                f"target {target.get('name', num_col)!r}: observed_series_file "
                f"{series_path} does not exist")
        if PFLOTRAN_TIME_COLUMN not in extracted or num_col not in extracted:
            raise KeyError(
                f"target {target.get('name', num_col)!r}: column {num_col!r} not in "
                f"extracted history {sorted(extracted)}")

        rho = float(target.get("water_density", PFLOTRAN_WATER_DENSITY))
        area = float(target.get("plan_area_m2", PFLOTRAN_PLAN_AREA_M2))
        start_h = float(target.get("experiment_start_h", PFLOTRAN_EXPERIMENT_START_H))

        time = np.asarray(extracted[PFLOTRAN_TIME_COLUMN], dtype=float)
        water = np.asarray(extracted[num_col], dtype=float)
        lo, hi = target.get("window", (float(time.min()), float(time.max())))  # HOURS

        in_window = (time >= lo) & (time <= hi)
        if not in_window.any():
            raise ValueError(
                f"target {target.get('name', num_col)!r}: window {lo}-{hi} h selects "
                f"no simulated time steps (tape spans {time.min()}-{time.max()} h). "
                f"NOTE PFLOTRAN windows are HOURS, not row indices.")
        order = np.argsort(time[in_window])
        sim_time_h = time[in_window][order]
        sim_flow_mm_h = -water[in_window][order] / rho / area * 1000.0

        measured = np.loadtxt(series_path)
        obs_hour = measured[:, 0] * 24.0 + start_h
        obs_flow = measured[:, 1]
        # NO ROW for the day-3-to-11 sensor outage (verified 20260813: the raw file
        # has no rows there at all, not zero-filled ones), so restricting to actual
        # measured rows + interpolation excludes that gap with no special-casing.
        obs_in_window = (obs_hour >= lo) & (obs_hour <= hi)
        obs_hour, obs_flow = obs_hour[obs_in_window], obs_flow[obs_in_window]
        if obs_hour.size == 0:
            raise ValueError(
                f"target {target.get('name', num_col)!r}: window {lo}-{hi} h selects "
                f"no measured points in {series_path.name}")

        # TRUNCATION IS CHECKED HERE, AFTER the observation-side check, and the order is a
        # judgement not an accident. "No measured points in the window" means the TARGET is
        # misconfigured -- a permanent error that no amount of waiting fixes. Truncation means the
        # RUN is incomplete -- transient, and re-scoring later resolves it. Reporting the permanent
        # fault first is more useful, and putting the truncation guard ahead of it masked exactly
        # that case in an existing test.
        self._assert_window_covered(target, time, lo, hi)

        sim_at_obs = np.interp(obs_hour, sim_time_h, sim_flow_mm_h,
                               left=np.nan, right=np.nan)
        valid = np.isfinite(sim_at_obs)
        if not valid.any():
            raise ValueError(
                f"target {target.get('name', num_col)!r}: no measured timestamp in "
                f"{series_path.name} falls inside the simulated series' own time "
                f"span ({sim_time_h.min()}-{sim_time_h.max()} h) within the window")

        cost_fn = CostFunction(method="nrmse", obs_type=ObservationType.TIME_SERIES,
                               normalization=NormalizationMethod.RANGE)
        nrmse = cost_fn.compute(sim_at_obs[valid], obs_flow[valid]).value
        return 1.0 + nrmse

    # ---- parameter writing (implemented, surface="primary" only) ----------
    #
    # The finite, closed vocabulary of leaf names the miniLEO param list uses,
    # longest-first so a future addition that happens to prefix a shorter
    # existing name (e.g. a hypothetical bare "PERMEABILITY") cannot be
    # mismatched against the wrong entry.
    _KNOWN_LEAF_NAMES: Tuple[str, ...] = tuple(sorted((
        "RATE_CONSTANT", "surface_area", "M", "ALPHA",
        "LIQUID_RESIDUAL_SATURATION", "PERM_ISO", "PERMEABILITY_POWER",
        "PERMEABILITY_CRITICAL_POROSITY", "LONGITUDINAL_DISPERSIVITY",
        "LIQUID_SATURATION",
    ), key=len, reverse=True))

    # PERM_ISO is sampled in log10 space (the param list's own header note)
    # because the deck reads it LINEARLY, unlike RATE_CONSTANT, where a
    # negative deck value is already reinterpreted as log10(k)
    # (reaction_mineral.F90:562-564) — every other name round-trips as-is.
    _LOG10_LEAF_NAMES = frozenset({"PERM_ISO"})

    @classmethod
    def _split_canonical_id(cls, key: str) -> Tuple[str, str]:
        """``'RATE_CONSTANT_Glass_FB'`` -> ``('RATE_CONSTANT', 'Glass_FB')``.

        Splitting on the RIGHTMOST underscore (EcoSIM's ``_MOD_PFT_RE``
        approach) is wrong here: several sub-addresses ARE mineral names that
        themselves contain underscores (``Glass_FB``, and the deck has
        ``Diopside_78_FB`` too, though it is excluded from this list). The
        split must match against the known, finite leaf-name vocabulary
        instead of guessing from the string's shape.
        """
        for leaf in cls._KNOWN_LEAF_NAMES:
            prefix = leaf + "_"
            if key.startswith(prefix):
                return leaf, key[len(prefix):]
        raise KeyError(
            f"{key!r} does not start with a known PFLOTRAN parameter name "
            f"{cls._KNOWN_LEAF_NAMES} — add it there if this is a genuinely "
            f"new knob, or it is a typo in the param list / modifications dict.")

    @staticmethod
    def _resolve_addresses(leaf: str, subaddr: str,
                           params: Dict[str, PFLOTRANParameter]) -> List[str]:
        """One param-list row -> one or more deck addresses.

        Matches by ADDRESS SUFFIX against the SAME parsed dict the writer
        uses below, rather than reconstructing ``format_address``'s grammar
        independently — a parser change and this resolver read one shared
        source of truth and cannot silently drift apart.
        """
        if leaf in ("M", "LIQUID_RESIDUAL_SATURATION") and subaddr.lower() == "all3":
            # ONE LOGICAL KNOB = THREE DECK ADDRESSES (SATURATION_FUNCTION +
            # both PERMEABILITY_FUNCTIONs) — the param list's own contract for
            # the sub-address literal "all3". Matches under ANY
            # CHARACTERISTIC_CURVES qualifier, which is correct for miniLEO's
            # single curve set ("sf1"); a deck with more than one
            # CHARACTERISTIC_CURVES block would need this narrowed to a
            # specific qualifier — this adapter does not have that case yet.
            return sorted(a for a in params
                          if a.endswith(f"/{leaf}") and "CHARACTERISTIC_CURVES" in a
                          and ("SATURATION_FUNCTION" in a or "PERMEABILITY_FUNCTION" in a))
        if leaf == "RATE_CONSTANT":
            want = f"MINERAL_KINETICS/{subaddr}/RATE_CONSTANT"
        elif leaf == "surface_area":
            want = f"MINERALS/{subaddr}#surface_area"
        elif leaf == "ALPHA":
            # Only one ALPHA card exists (under SATURATION_FUNCTION; the
            # permeability functions don't carry one), so subaddr ("sf" in
            # the param list) is documentation only and not needed to resolve.
            want = "SATURATION_FUNCTION[VAN_GENUCHTEN]/ALPHA"
        elif leaf == "PERM_ISO":
            want = f"MATERIAL_PROPERTY[{subaddr}]/PERMEABILITY/PERM_ISO"
        elif leaf in ("PERMEABILITY_POWER", "PERMEABILITY_CRITICAL_POROSITY",
                      "LONGITUDINAL_DISPERSIVITY"):
            want = f"MATERIAL_PROPERTY[{subaddr}]/{leaf}"
        elif leaf == "LIQUID_SATURATION":
            want = f"FLOW_CONDITION[{subaddr}]/LIQUID_SATURATION"
        else:
            raise KeyError(f"no address rule for leaf {leaf!r} (sub-address {subaddr!r})")

        matches = [a for a in params if a.endswith(want)]
        if len(matches) > 1:
            raise ValueError(f"ambiguous address for {leaf}[{subaddr}]: {matches}")
        return matches

    def write_parameter_file(self, base_param_file: Path, modifications: Dict[str, Any],
                             output_path: Path, surface: str = "primary") -> None:
        """Apply calibration parameter modifications to the deck and write the result.

        LINE-SURGICAL, not a full re-serialization: parses the base deck to
        locate each modified card's exact line and original token
        (``PFLOTRANParameter.raw``/``.line``), then replaces only that token,
        leaving comments, whitespace and every untouched card byte-identical.
        The deck is a free-form, hand-tuned per-case file (its own header
        records ``calibration_..._021`` — 21+ manual iterations) that a
        generic round-trip writer would not reproduce faithfully.

        This design also satisfies the DBASE_VALUE hazard the previous
        version of this method warned about without implementing anything: an
        address this resolver never touches is never at risk, and any address
        it DOES touch is checked for ``writable`` first (none of the current
        16-parameter list are DBASE_VALUE references, verified against the
        miniLEO deck, but a future param list might add one).

        ``modifications`` keys are the calibration layer's canonical ids,
        ``{name}_{pft}`` per the param list's own convention (e.g.
        ``RATE_CONSTANT_Glass_FB``, ``M_all3``, ``PERM_ISO_Bolitic``).
        """
        if surface != "primary":
            raise NotImplementedError(
                "Only surface='primary' (the pflotran.in card deck) is "
                "implemented. surface='database' (savannah_river.dat, the "
                "thermodynamic Keq/stoichiometry) has no calibration knobs in "
                "the current 16-parameter list ('the DATABASE is fixed input' "
                "— the param list's own EXCLUDED section) and is out of scope "
                "until one is added.")

        base_param_file = Path(base_param_file)
        output_path = Path(output_path)
        params = PFLOTRANParameterParser().parse(base_param_file)

        lines = base_param_file.read_text(errors="replace").splitlines(keepends=True)
        edits: Dict[int, Tuple[str, str]] = {}   # 1-based line -> (old_token, new_token)

        for key, new_value in modifications.items():
            leaf, subaddr = self._split_canonical_id(key)
            addrs = self._resolve_addresses(leaf, subaddr, params)
            if not addrs:
                raise KeyError(
                    f"{key!r} resolved to no address in {base_param_file.name} "
                    f"(leaf={leaf!r}, subaddr={subaddr!r})")
            val = 10.0 ** float(new_value) if leaf in self._LOG10_LEAF_NAMES else float(new_value)
            new_token = f"{val:.10g}"
            for addr in addrs:
                prm = params[addr]
                if not prm.writable:
                    raise ValueError(
                        f"{key!r} resolves to {addr}, a DBASE_VALUE reference — "
                        "not writable (input_aux.F90:474-478); overwriting it "
                        "would silently corrupt every realization.")
                if prm.line in edits and edits[prm.line][1] != new_token:
                    raise ValueError(
                        f"line {prm.line} ({addr}) already scheduled for a "
                        f"different value ({edits[prm.line][1]}) — two "
                        "modification keys collided on one deck address")
                edits[prm.line] = (prm.raw, new_token)

        for lineno, (old_token, new_token) in edits.items():
            idx = lineno - 1
            line = lines[idx]
            # Replace the first WORD-BOUNDARY occurrence of the original
            # token, so e.g. rewriting "3" never touches a "3" that is a
            # substring of a longer number or unit string on the same line.
            # Scoped correctness note: this assumes each edited field's raw
            # token is unique on its own line, true for every card this
            # resolver currently addresses (verified against the miniLEO
            # deck); a future field sharing a line with an identical-valued
            # neighbour would need position tracking instead.
            pattern = re.compile(r"(?<![\w.+-])" + re.escape(old_token) + r"(?![\w.])")
            new_line, n = pattern.subn(new_token, line, count=1)
            if n == 0:
                raise ValueError(
                    f"line {lineno}: could not find original token {old_token!r} "
                    f"to replace (deck changed since parsing?) — line was: {line!r}")
            lines[idx] = new_line

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("".join(lines))

    # ---- case creation (implemented) --------------------------------------
    def create_case(self, case_name: str, param_file: Path, config: Dict[str, Any],
                    secondary_param_file: Optional[Path] = None) -> Path:
        """Assemble a case directory around an ALREADY-WRITTEN per-case deck.

        By the calling convention `scripts/materialize_adapter_ensemble.py` uses
        (the only orchestrator that calls this today), ``param_file`` is not a
        template to copy — it is the PERTURBED deck, already written by
        ``write_parameter_file`` directly at ``run_root/case_name/<deck name>``.
        This method's job is narrower: stage the static, per-round-constant
        supporting files (mesh, boundary sidesets, restart checkpoint, rainfall
        forcing, the thermodynamic database) alongside it, and render the
        submit script.

        ``secondary_param_file`` is rejected: PFLOTRAN's only second surface
        (the database) has no calibration knobs in the current param list —
        see ``write_parameter_file``'s ``surface='database'`` guard.

        RESTART CAVEAT (not resolved here, by design): every case stages the
        SAME pre-steady-state restart checkpoint, produced under the base
        parameter set. A member that perturbs porosity/permeability/the van
        Genuchten curve/the mineral assemblage restarts from a state that is
        no longer strictly consistent with its own parameters. Whether that
        is an acceptable approximation for a Morris/Sobol screen or every
        member needs its own spin-up is an ensemble-design decision for the
        PI, not a mechanical concern this method can resolve.
        """
        if secondary_param_file is not None:
            raise NotImplementedError(
                "PFLOTRAN has no secondary surface with a calibration knob yet "
                "-- see write_parameter_file's surface='database' guard.")

        param_file = Path(param_file)
        case_dir = param_file.parent
        case_dir.mkdir(parents=True, exist_ok=True)

        base_param_file = config.get("A2MC_BASE_PARAM_FILE")
        if not base_param_file:
            raise KeyError(
                "config['A2MC_BASE_PARAM_FILE'] is required -- it names the base "
                "case directory (mesh/restart/rainfall/database live beside it) "
                "and is set by the site config (source it first).")
        src_dir = Path(base_param_file).parent

        for src in sorted(src_dir.iterdir()):
            if src.is_dir():
                continue                            # e.g. the base case's own 'output/'
            if src.name == param_file.name:
                continue                            # the perturbed deck is already staged
            dst = case_dir / src.name
            if not dst.exists():
                shutil.copy2(src, dst)

        tmpl_path = Path(
            config.get("A2MC_PFLOTRAN_RUNTEMPLATE")
            or (Path(__file__).parent / "runtemplates" / "hpc_standalone.sh.tmpl"))
        submit = case_dir / "submit.sh"
        if tmpl_path.exists():
            submit.write_text(self._render_template(tmpl_path.read_text(), case_name, case_dir,
                                                     param_file, config))
            submit.chmod(0o755)
        return case_dir

    def _render_template(self, tmpl: str, case_name: str, case_dir: Path,
                         deck_path: Path, config: Dict[str, Any]) -> str:
        subs = {
            "CASE_NAME": case_name,
            "ACCOUNT": config.get("A2MC_HPC_ACCOUNT", "m5199"),
            "QUEUE": config.get("A2MC_HPC_QUEUE", "regular"),
            "NODES": config.get("A2MC_HPC_NODES", "1"),
            "MPI_RANKS": config.get("A2MC_HPC_MPI_RANKS", "1"),
            "CPUS_PER_TASK": config.get("A2MC_HPC_CPUS_PER_TASK", "1"),
            "WALLTIME": config.get("A2MC_HPC_WALLTIME", "02:00:00"),
            "OUTPUT_DIR": str(case_dir),
            "OMP_NUM_THREADS": config.get("A2MC_OMP_NUM_THREADS", "1"),
            "MODEL_BINARY": config.get("A2MC_PFLOTRAN_BINARY", "pflotran"),
            "RUN_CMD": str(deck_path),          # the template's DECK={{RUN_CMD}}
            "MODULES": config.get("A2MC_PFLOTRAN_MODULES", "# no module load required at runtime"),
            "PRE_RUN_HOOK": config.get("A2MC_PFLOTRAN_PRE_RUN_HOOK", "# (none)"),
            "POST_RUN_HOOK": config.get("A2MC_PFLOTRAN_POST_RUN_HOOK", "# (none)"),
        }
        out = tmpl
        for k, v in subs.items():
            out = out.replace("{{" + k + "}}", str(v))
        return out

    # ---- submission (implemented) ------------------------------------------
    def submit_ensemble(self, case_paths: List[Path], config: Dict[str, Any]) -> List[str]:
        """sbatch each case's submit.sh. Dry-run (no sbatch on PATH, or
        A2MC_DRY_RUN truthy) returns synthetic DRYRUN-* ids without touching
        the scheduler."""
        dry = str(config.get("A2MC_DRY_RUN", "")).strip().lower() in ("1", "true", "yes") \
            or not shutil.which("sbatch")
        job_ids: List[str] = []
        for i, cp in enumerate(case_paths):
            submit = Path(cp) / "submit.sh"
            if not submit.exists():
                raise FileNotFoundError(f"no submit.sh in case {cp}")
            if dry:
                jid = f"DRYRUN-{i:04d}"
            else:
                res = subprocess.run(
                    ["sbatch", "--parsable", str(submit)],
                    cwd=str(cp), capture_output=True, text=True)
                if res.returncode != 0:
                    raise RuntimeError(f"sbatch failed for {cp}: {res.stderr.strip()}")
                jid = res.stdout.strip().split(";")[0]
            (Path(cp) / "job_id.txt").write_text(jid + "\n")
            job_ids.append(jid)
        return job_ids

    def list_diagnostic_tools(self) -> List[Path]:
        return []
