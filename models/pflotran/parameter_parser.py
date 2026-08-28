"""PFLOTRAN parameter parser — reads a PFLOTRAN input deck.

PFLOTRAN has no parameter FILE in the FATES/EcoSIM sense. Its parameter surface
is the **input deck**: a free-form nested card language, per-case, where a knob
is addressed by its block path rather than a bare name:

    CHEMISTRY/MINERAL_KINETICS/Glass_FB/RATE_CONSTANT               = -12.6349
    MATERIAL_PROPERTY[Bolitic]/PERMEABILITY/PERM_ISO                = 1.188d-11
    CHARACTERISTIC_CURVES[sf1]/SATURATION_FUNCTION[VAN_GENUCHTEN]/M = 0.4505494
    CONSTRAINT[initial]/MINERALS/Labradorite#vol_frac               = 0.144

Design + validation: `memory/dev_logs_adapterkitpflotran/20260730d` (address form,
five grammar classes) and `20260731e` (v2 — five reader-semantics refutations
found by reading the source at 157a26f7). Every non-obvious rule below is cited
to PFLOTRAN source so the claim is checkable.

Contract (docs/19 §6.5 + `tools/adapter_conformance_validator.py`): no-arg
``__init__`` + ``parse(file_path)``.

SOURCE-NAME-WINS. Where the upstream docs and the source disagree on a card name,
the SOURCE name is authoritative — the docs describe intent, the reader defines
what is accepted (`20260731f`: 95 % agree, and the six mismatches include two
plain doc typos).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------- grammar ----
# Keywords that OPEN a block. Seeded from the deck + the docs-mined registry
# (`20260731a`), and deliberately a UNION of both: the docs alone miss 8 real
# blocks, and the deck alone misses everything it happens not to use.
BLOCK_KEYWORDS = {
    "SIMULATION", "PROCESS_MODELS", "SUBSURFACE_FLOW", "SUBSURFACE_TRANSPORT",
    "OPTIONS", "RESTART", "CHECKPOINT", "FLUID_PROPERTY", "EOS", "GRID",
    "CHEMISTRY", "PRIMARY_SPECIES", "SECONDARY_SPECIES", "PASSIVE_GAS_SPECIES",
    "ACTIVE_GAS_SPECIES", "MINERALS", "MINERAL_KINETICS", "OUTPUT",
    "NUMERICAL_METHODS", "TIMESTEPPER", "NEWTON_SOLVER", "LINEAR_SOLVER",
    "TIME", "CONSTRAINT", "CONCENTRATIONS", "REGION", "FLOW_CONDITION",
    "TRANSPORT_CONDITION", "CONSTRAINT_LIST", "TYPE", "INITIAL_CONDITION",
    "BOUNDARY_CONDITION", "SOURCE_SINK", "MATERIAL_PROPERTY", "PERMEABILITY",
    "CHARACTERISTIC_CURVES", "SATURATION_FUNCTION", "PERMEABILITY_FUNCTION",
    "STRATA", "OBSERVATION_FILE", "MASS_BALANCE_FILE", "SNAPSHOT_FILE",
    "VARIABLES", "TOTAL_MASS_REGIONS", "DEBUG", "SUBSURFACE",
    "ISOTHERM_REACTIONS", "MINERAL_NUCLEATION_KINETICS", "COMPLEX_KINETICS",
}

FLAG_KEYWORDS = {
    "ISOTHERMAL", "IMMISCIBLE", "NO_TEMP_DEPENDENT_DIFFUSION", "SKIP_RESTART",
    "USE_MILLINGTON_QUIRK_TORTUOSITY", "RESET_TO_TIME_ZERO", "SMOOTH",
    "LOG_FORMULATION", "UPDATE_POROSITY", "UPDATE_PERMEABILITY", "INFINITE",
    "GAS_TRANSPORT_IS_UNVETTED", "VELOCITY_AT_CENTER", "DETAILED",
    "GASES", "MINERAL_SATURATION_INDEX", "MINERAL_SURFACE_AREA", "TOTAL",
    "FREE_ION", "PH", "TOTAL_SORBED", "KD", "TOTAL_SORBED_MOBILE",
    "EQUILIBRATE_AT_EACH_CELL",
}

# Class 1 — the SAME keyword changes role by parent block. There is no central
# card dispatch table in PFLOTRAN (397 independent `InputKeywordUnrecognized`
# sites; `grep card_table|keyword_table|dispatch` returns zero), so each block
# reader parses its own block and context must be modelled here.
NOT_A_BLOCK_IN = {
    "INITIAL_CONDITION":   {"FLOW_CONDITION", "TRANSPORT_CONDITION", "REGION"},
    "BOUNDARY_CONDITION":  {"FLOW_CONDITION", "TRANSPORT_CONDITION", "REGION"},
    "SOURCE_SINK":         {"FLOW_CONDITION", "TRANSPORT_CONDITION", "REGION"},
    "STRATA":              {"MATERIAL", "REGION"},
    "MATERIAL_PROPERTY":   {"CHARACTERISTIC_CURVES"},
    "OUTPUT":              {"PRIMARY_SPECIES", "SECONDARY_SPECIES", "MINERALS",
                            "GASES", "TOTAL", "FREE_ION"},
}
# `TYPE` lists variable/condition-type pairs in FLOW_CONDITION but is a scalar in
# GRID ("TYPE UNSTRUCTURED <file>") and TRANSPORT_CONDITION. `MODE` likewise is a
# scalar selector in SUBSURFACE_FLOW.
BLOCK_ONLY_IN = {"TYPE": {"FLOW_CONDITION"}, "MODE": set()}

# Class 5 — children are always bare data names. Critical because some listed
# names collide with block keywords (OUTPUT/VARIABLES lists PERMEABILITY).
NAME_LIST_BLOCKS = {"VARIABLES", "TOTAL_MASS_REGIONS", "PRIMARY_SPECIES",
                    "SECONDARY_SPECIES", "PASSIVE_GAS_SPECIES", "ACTIVE_GAS_SPECIES"}

# Class 2 — inside these, a bare token opens a sub-block NAMED BY THE DATA.
DYNAMIC_KEY_BLOCKS = {"MINERAL_KINETICS", "ISOTHERM_REACTIONS",
                      "MINERAL_NUCLEATION_KINETICS", "COMPLEX_KINETICS"}

# Class 4 — parsed for nesting, contribute nothing to an address.
TRANSPARENT_BLOCKS = {"SIMULATION", "SUBSURFACE"}

# R1 (20260731e) — SUBSURFACE has NO InputCheckExit; a bare '/' or 'END' inside it
# is FATAL (factory_subsurface_read.F90:2572-2577), unlike SIMULATION one level up
# which does use one (factory_forward.F90:143). The two outermost blocks behave
# OPPOSITELY.
ENDONLY_BLOCKS = {"SUBSURFACE"}

# R5 — any int/real/NAME slot may hold this instead of a literal, resolved from a
# separate file by realization index (input_aux.F90:474-478, 2193-2227). A writer
# that overwrites it as if it held a number SILENTLY CORRUPTS THE DECK.
DBASE_TOKEN = "DBASE_VALUE"

# Class 3 — positional rows: (field, kind). "num" -> a knob; "tok" -> metadata.
POSITIONAL_BLOCKS = {
    "MINERALS": [("vol_frac", "num"), ("surface_area", "num"), ("area_units", "tok")],
    "CONCENTRATIONS": [("value", "num"), ("constraint_type", "tok"), ("aux", "tok")],
}
# R4 — constraint type codes (transport_constraint_rt.F90:306-346), case-insensitive.
CONSTRAINT_TYPES = {
    "F": 1, "FREE": 1, "T": 2, "TOTAL": 2, "L": 3, "LOG": 3, "P": 4, "PH": 4,
    "E": 5, "PE": 5, "M": 7, "MINERAL": 7, "MNRL": 7, "G": 8, "GAS": 8,
    "Z": 9, "CHARGE_BALANCE": 9, "TOTAL_SORB": 10, "SC": 11,
    "TOTAL_AQ_PLUS_SORB": 12,
}
CONSTRAINT_TYPES_REMOVED = {"S"}          # removed upstream, fatal (:323-326)
CONSTRAINT_TYPES_NEED_AUX = {"M", "MINERAL", "MNRL", "G", "GAS", "SC"}

# R3 — StringStartsWith truncates to min length (string.F90:444), so a line
# containing only 'E' or 'EN' also terminates. 'ENDIF' does not.
_END_PREFIXES = {"E", "EN", "END"}
_NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([dDeE][+-]?\d+)?$")

# Keyword -> category (mirrors PFLOTRAN_SPEC.param_categories).
_CATEGORY_RULES: Tuple[Tuple[str, str], ...] = (
    ("RATE_CONSTANT", "mineral_kinetics"),
    ("SURFACE_AREA", "mineral_kinetics"),
    ("AFFINITY", "mineral_kinetics"),
    ("MINERAL", "mineral_kinetics"),
    ("VAN_GENUCHTEN", "water_retention"),
    ("SATURATION_FUNCTION", "water_retention"),
    ("RESIDUAL_SATURATION", "water_retention"),
    ("ALPHA", "water_retention"),
    ("PERMEABILITY", "permeability"),
    ("PERM_", "permeability"),
    ("POROSITY", "porosity"),
    ("DISPERSIVITY", "transport"),
    ("DIFFUSION", "transport"),
    ("CONCENTRATIONS", "chemistry"),
    ("CONSTRAINT", "boundary"),
    ("FLOW_CONDITION", "boundary"),
    ("TIMESTEP", "solver"), ("NEWTON", "solver"), ("MAX_", "solver"),
    ("NUMERICAL_METHODS", "solver"), ("TIME", "solver"),
)
# Categories that are genuine calibration knobs (vs run-control).
_CALIBRATABLE = {"mineral_kinetics", "water_retention", "permeability",
                 "porosity", "transport", "chemistry", "boundary"}


def _strip_comment(line: str) -> str:
    """PFLOTRAN uses BOTH '#' and '!', inline too, and is quote/escape-BLIND
    (input_aux.F90:797, :854-864) — a '#' inside a filename truncates it."""
    for c in ("#", "!"):
        i = line.find(c)
        if i != -1:
            line = line[:i]
    return line.strip()


def _is_number(tok: str) -> bool:
    return bool(_NUM_RE.match(tok))


def _to_float(tok: str) -> Optional[float]:
    return None if not _is_number(tok) else float(tok.replace("d", "e").replace("D", "e"))


def _is_terminator(tok: str) -> bool:
    return tok == "/" or tok.upper() in _END_PREFIXES


def format_address(stack: List[Tuple[str, str]], leaf: str, field_name: str = "") -> str:
    """CARD[qual]/SUB[qual]/LEAF[#field]. Shared with the backend writer so parse
    and write use ONE addressing scheme (the ATS pattern)."""
    parts = [f"{n}[{q}]" if q else n for n, q in stack if n not in TRANSPARENT_BLOCKS]
    addr = "/".join([*parts, leaf])
    return f"{addr}#{field_name}" if field_name else addr


def _classify(address: str, leaf: str) -> str:
    hay = f"{address} {leaf}".upper()
    for kw, cat in _CATEGORY_RULES:
        if kw in hay:
            return cat
    return ""


@dataclass
class PFLOTRANParameter:
    """One addressable deck knob."""
    name: str                       # the full address (unique key)
    leaf: str                       # the card keyword (or row label)
    block: str                      # immediate parent block
    value: Optional[float]
    raw: str
    units: str = ""
    line: int = 0
    kind: str = "keyvalue"          # keyvalue | positional | dbase_ref
    field_name: str = ""
    writable: bool = True           # False for a DBASE_VALUE reference (R5)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def long_name(self) -> str:
        """Human-readable description, for RAG chunk text and any consumer that
        wants more than an address.

        DERIVED FROM THE DECK, NOT FROM THE CURATED SEED — deliberately. The V2
        validator dispatches through this parser to check the seed, so a parser
        that read the seed would make that check circular. The deck's own block
        chain is real information anyway: for a MINERAL_KINETICS card the parent
        segment IS the mineral the constant belongs to, and for a CONSTRAINT row
        the label is the mineral and the field is the column.

        (Added 2026-08-01: `long_name` was declared on this record and populated
        on 0 of 121, which `tools/validate_adapter_parser_contract.py` flagged on
        its first run against this adapter. A field that is always empty is
        indistinguishable from a missing one, and RAG text degrades silently.)
        """
        parent = self.name.rsplit("/", 1)[0] if "/" in self.name else ""
        units = f" [{self.units}]" if self.units else ""
        cat = f" [{self.category}]" if self.category else ""
        where = f" (deck line {self.line})" if self.line else ""

        if self.kind == "positional":
            # e.g. vol_frac column of the MINERALS row 'Labradorite' under CONSTRAINT[initial]
            # `parent` already ends in the block, so drop that segment to avoid
            # "the MINERALS row ... under .../MINERALS".
            grandparent = parent
            if grandparent.endswith("/" + self.block):
                grandparent = grandparent[: -(len(self.block) + 1)]
            base = (f"{self.field_name} column of the {self.block} row "
                    f"{self.leaf!r}")
            if grandparent:
                base += f" under {grandparent}"
        elif self.kind == "dbase_ref":
            base = (f"{self.leaf} card under {parent}" if parent
                    else f"{self.leaf} card")
            base = f"DATABASE-valued {base}"
        else:
            base = (f"{self.leaf} card under {parent}" if parent
                    else f"{self.leaf} card")

        if not self.writable:
            base = f"READ-ONLY {base}"
        return f"{base}{units}{cat}{where}"

    @property
    def category(self) -> str:
        return _classify(self.name, self.leaf)

    @property
    def category_key(self) -> str:
        return self.category

    @property
    def is_calibratable(self) -> bool:
        return self.writable and self.category in _CALIBRATABLE

    @property
    def is_pft_specific(self) -> bool:
        return False                # PFLOTRAN has no PFT axis; grouping is by region

    @property
    def is_scalar(self) -> bool:
        return self.value is not None

    @property
    def is_string(self) -> bool:
        return self.value is None

    def __repr__(self) -> str:      # pragma: no cover
        return f"<PFLOTRANParameter {self.name}={self.raw}>"


class PFLOTRANParameterParser:
    """Parses a PFLOTRAN input deck into address -> PFLOTRANParameter."""

    def __init__(self):
        self._params: Dict[str, PFLOTRANParameter] = {}
        self.warnings: List[str] = []
        self.errors: List[str] = []

    # -- public ------------------------------------------------------------
    def parse(self, file_path) -> Dict[str, PFLOTRANParameter]:
        path = Path(file_path)
        self._params, self.warnings, self.errors = {}, [], []
        stack: List[Tuple[str, str]] = []
        open_lines: List[int] = []

        for lineno, raw in enumerate(path.read_text(errors="replace").splitlines(), 1):
            line = _strip_comment(raw)
            if not line:
                continue
            toks = line.split()
            head = toks[0].upper()
            cur = stack[-1][0] if stack else ""

            if _is_terminator(toks[0]) and len(toks) == 1:
                self._close(stack, open_lines, toks[0], lineno)
                continue
            if head.startswith("END_"):
                if stack and stack[-1][0] == head[4:]:
                    stack.pop(); open_lines.pop()
                continue
            if cur in POSITIONAL_BLOCKS and head not in BLOCK_KEYWORDS:
                self._positional(stack, cur, toks, lineno)
                continue
            if cur in NAME_LIST_BLOCKS:
                continue
            if cur in DYNAMIC_KEY_BLOCKS and head not in BLOCK_KEYWORDS and len(toks) == 1:
                stack.append((toks[0], "")); open_lines.append(lineno)
                continue
            restricted = BLOCK_ONLY_IN.get(head)
            if (head in BLOCK_KEYWORDS and head not in FLAG_KEYWORDS
                    and head not in NOT_A_BLOCK_IN.get(cur, set())
                    and (restricted is None or cur in restricted)):
                qual = toks[1] if len(toks) > 1 else ""
                if not (qual and _is_number(qual)):
                    stack.append((head, qual)); open_lines.append(lineno)
                    continue
            if head in FLAG_KEYWORDS or len(toks) == 1:
                continue
            self._keyvalue(stack, cur, head, toks, lineno)

        if stack:
            unclosed = ", ".join(f"{n}[{q}]@L{l}" for (n, q), l in zip(stack, open_lines))
            raise ValueError(
                f"UNBALANCED DECK: {len(stack)} block(s) never closed: {unclosed}. "
                "This means the grammar registry is incomplete for this deck — fail "
                "loud rather than mis-attribute cards to the wrong block.")
        return self._params

    def calibration_parameters(self, file_path) -> Dict[str, PFLOTRANParameter]:
        return {k: v for k, v in self.parse(file_path).items() if v.is_calibratable}

    def get_pft_count(self) -> int:
        return 0                    # no PFT axis

    # -- internals ---------------------------------------------------------
    def _close(self, stack, open_lines, tok, lineno) -> None:
        if not stack:
            # A stray terminator at top level has no parent to mis-close. INSIDE a
            # block the same surplus terminator silently closes the PARENT and
            # re-parents its remaining cards (input_aux.F90:1493-1534) — there is
            # no tolerance code in PFLOTRAN at all.
            self.warnings.append(f"L{lineno}: stray '{tok}' at top level")
            return
        if stack[-1][0] in ENDONLY_BLOCKS:
            self.errors.append(
                f"L{lineno}: bare '{tok}' inside {stack[-1][0]}, which has no "
                f"InputCheckExit — PFLOTRAN would ABORT here. Use END_{stack[-1][0]}.")
            return
        stack.pop(); open_lines.pop()

    def _positional(self, stack, cur, toks, lineno) -> None:
        fields = POSITIONAL_BLOCKS[cur]
        label, rest = toks[0], toks[1:]
        meta: Dict[str, Any] = {}
        nums: List[Tuple[str, str]] = []
        for (fname, kind), tok in zip(fields, rest):
            if kind == "num":
                if _is_number(tok):
                    nums.append((fname, tok))
                elif tok.upper() == DBASE_TOKEN:
                    meta[fname] = DBASE_TOKEN
                    self.warnings.append(
                        f"L{lineno}: {label}.{fname} is a {DBASE_TOKEN} reference — not writable")
            else:
                meta[fname] = tok
        ctype = meta.get("constraint_type")
        if ctype:
            cu = ctype.upper()
            if cu in CONSTRAINT_TYPES_REMOVED:
                self.errors.append(f"L{lineno}: constraint type '{ctype}' was removed upstream (fatal)")
            elif cu not in CONSTRAINT_TYPES:
                self.warnings.append(f"L{lineno}: unrecognised constraint type '{ctype}' on {label}")
            elif cu in CONSTRAINT_TYPES_NEED_AUX and not meta.get("aux"):
                self.errors.append(
                    f"L{lineno}: constraint type '{ctype}' on {label} REQUIRES a 4th column "
                    "naming the constraining mineral/gas")
        for fname, raw in nums:
            addr = format_address(stack, label, fname)
            self._params[addr] = PFLOTRANParameter(
                name=addr, leaf=label, block=cur, value=_to_float(raw), raw=raw,
                units=meta.get("area_units", "") if fname == "surface_area" else "",
                line=lineno, kind="positional", field_name=fname,
                meta={k: v for k, v in meta.items() if k != "area_units"})

    def _keyvalue(self, stack, cur, head, toks, lineno) -> None:
        addr = format_address(stack, head)
        if toks[1].upper() == DBASE_TOKEN:
            self._params[addr] = PFLOTRANParameter(
                name=addr, leaf=head, block=cur, value=None,
                raw=" ".join(toks[1:3]), line=lineno, kind="dbase_ref", writable=False)
            self.warnings.append(f"L{lineno}: {addr} is a {DBASE_TOKEN} reference — not writable")
            return
        val = _to_float(toks[1])
        if val is None:
            return                                  # non-numeric (FILE <name>, DIRICHLET, …)
        if addr in self._params:
            # Anonymous repeated blocks collide: two `FLUID_PROPERTY` blocks differ
            # only by an inner `PHASE` card, and their diffusion coefficients differ
            # by four orders of magnitude. Discriminator support is not implemented
            # (20260730d §5) — warn rather than silently keep one.
            self.warnings.append(f"L{lineno}: duplicate address {addr} (first wins) — "
                                 "anonymous repeated block needs a discriminator")
            return
        unit = toks[2] if len(toks) > 2 and not _is_number(toks[2]) else ""
        self._params[addr] = PFLOTRANParameter(
            name=addr, leaf=head, block=cur, value=val, raw=toks[1],
            units=unit, line=lineno, kind="keyvalue")
