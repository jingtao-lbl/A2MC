#!/usr/bin/env python
"""Resolve EcoSIM parameter-file names to every source site that reads and uses them, at one COMMIT.

visibility: public
Author: Jing Tao with Claude on Perlmutter

WHY THIS EXISTS. A calibration parameter is a name in a NetCDF file; what it does is decided by the
Fortran variable it is read into and by every routine that variable reaches. Three things make that
mapping easy to get wrong by hand, and each has already happened in this repo:

  * EcoSIM reads the plant file through TWO paths (`PlantInfoMod.F90`: a per-PFT reader indexed by
    `loc`, and a table reader into `*_tab` arrays that `SetPlantTraits` later copies into `*_pft`),
    so a grep for one target misses the other.
  * Plant routines rename variables in `associate(alias => obj%Var)` blocks, so a grep for the
    stored name misses the physics that uses the alias.
  * A parameter can be read and then OVERWRITTEN (`RSRA`, recomputed in STARTQ from `ARSRA`), or be
    read in several routines that parallel type flags select between (`CHL` in C3 and C4 branches).

This tool answers the question from the source itself, at an exact commit, through `git grep` and
`git show` (index-based, so it is compliant with the NERSC no-recursive-traversal rule), and emits
JSON for validators and a Markdown page for the wiki. It never decides what a site MEANS; it lists
where the parameter goes, with the enclosing routine of every site, so a curated claim can cite it
and a validator can check the citation.

Run:
  python tools/ecosim_param_source_map.py --model-path $A2MC_MODEL_PATH --commit cb243228 \\
      --param-list use_cases/EcoSIM_Lusignan/parameters/ecosim_lusignan_param_list_r02b.csv \\
      --json tmp/source_map.json --markdown <wiki>/reference/calibration_parameter_source_map.md
"""
from __future__ import annotations

import argparse
import csv
import functools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# `module procedure X` opens a SUBMODULE body (closed by `end procedure`), e.g. the history update
# routines in f90src/IOutils/HistData/; without it, a line there resolved to the wrong routine.
ROUTINE_HDR = re.compile(r"^\s*(?:(?:recursive|pure|elemental|impure|module)\s+)*"
                         r"(?:subroutine|function|procedure)\s+([A-Za-z_]\w*)", re.I)
ROUTINE_END = re.compile(r"^\s*end\s+(?:subroutine|function|procedure)\b", re.I)
GETVAR = re.compile(r"ncd_getvar\s*\(\s*([^,]+?)\s*,\s*'([A-Za-z0-9_]+)'\s*,(.*)$", re.I)
IO_FILES = ("RestartMod.F90", "restUtilMod.F90", "HistDataType.F90", "HistFileMod.F90")


class Source:
    """Read-only, commit-addressed view of a git checkout."""

    def __init__(self, root: str, commit: str):
        self.root, self.commit = root, commit
        full = self._git("rev-parse", "--verify", f"{commit}^{{commit}}").strip()
        if not full:
            raise SystemExit(f"commit {commit!r} not found in {root}")
        self.full = full

    def _git(self, *args) -> str:
        r = subprocess.run(["git", "-C", self.root, *args], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, universal_newlines=True)
        return r.stdout

    def grep(self, pattern: str, *flags) -> list[tuple[str, int, str]]:
        """[(path, line, text)] for `git grep -n <flags> -e pattern <commit> -- *.F90`."""
        out = self._git("grep", "-n", *flags, "-e", pattern, self.commit, "--", "*.F90", "*.f90")
        hits = []
        pre = self.commit + ":"
        for ln in out.splitlines():
            if ln.startswith(pre):
                ln = ln[len(pre):]
            path, no, text = ln.split(":", 2)
            hits.append((path, int(no), text))
        return hits

    @functools.lru_cache(maxsize=None)
    def lines(self, path: str) -> tuple[str, ...]:
        return tuple(self._git("show", f"{self.commit}:{path}").splitlines())

    def exists(self, path: str) -> bool:
        return bool(self._git("ls-tree", "--name-only", self.commit, "--", path).strip())

    @functools.lru_cache(maxsize=None)
    def path_index(self) -> dict:
        """basename -> [repo paths], so a citation written with a bare filename can be resolved."""
        idx: dict = {}
        for p in self._git("ls-tree", "-r", "--name-only", self.commit).splitlines():
            if p.lower().endswith((".f90",)):
                idx.setdefault(os.path.basename(p), []).append(p)
        return idx

    def resolve(self, cited: str) -> list[str]:
        """A cited path may be repo-relative or a bare basename; return every matching repo path."""
        if self.exists(cited):
            return [cited]
        return list(self.path_index().get(os.path.basename(cited), []))


def enclosing_routine(lines, lineno: int) -> str:
    """Walk BACKWARDS from `lineno` (1-based) to the nearest routine header. Meeting an `end
    subroutine` first means the line is at module scope. A forward scan finds the NEXT routine."""
    for i in range(min(lineno, len(lines)) - 1, -1, -1):
        s = lines[i]
        if i != lineno - 1 and ROUTINE_END.match(s):
            return "<module scope>"
        m = ROUTINE_HDR.match(s)
        if m and not re.match(r"^\s*end\b", s, re.I):
            return m.group(1)
    return "<module scope>"


def routine_span(lines, lineno: int) -> tuple[int, int]:
    """(first, last) 1-based lines of the routine enclosing `lineno`."""
    start = 1
    for i in range(min(lineno, len(lines)) - 1, -1, -1):
        if ROUTINE_HDR.match(lines[i]) and not re.match(r"^\s*end\b", lines[i], re.I):
            start = i + 1
            break
    end = len(lines)
    for j in range(lineno - 1, len(lines)):
        if ROUTINE_END.match(lines[j]):
            end = j + 1
            break
    return start, end


def _target(argtail: str) -> str | None:
    """Last top-level argument of an ncd_getvar call, stripped of its index: the variable read."""
    depth, parts, cur = 0, [], ""
    for ch in argtail:
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    last = parts[-1].strip()
    m = re.match(r"([A-Za-z_][\w%]*)", last)
    return m.group(1).split("%")[-1] if m else None


def file_reads(src: Source) -> dict:
    """{NAME: [{file, line, routine, target}]} for every name-literal ncd_getvar read."""
    reads: dict = {}
    for path, no, text in src.grep(r"ncd_getvar", "-i"):
        lines = src.lines(path)
        full = text
        k = no
        while full.rstrip().endswith("&") and k < len(lines):     # Fortran continuation
            full = full.rstrip()[:-1] + " " + lines[k].lstrip().lstrip("&")
            k += 1
        m = GETVAR.search(full)
        if not m:
            continue
        name, tgt = m.group(2), _target(m.group(3))
        routine = enclosing_routine(lines, no)
        prev = " ".join(lines[max(0, no - 3):no - 1]) + " " + text.split("ncd_getvar")[0]
        conditional = bool(re.search(rf"check_var\s*\([^)]*'{name}'", prev, re.I)
                           or re.match(r"\s*if\s*\(", text, re.I))
        reads.setdefault(name, []).append(
            {"file": path, "line": no, "routine": routine, "target": tgt,
             "live": routine_is_referenced(src, routine), "conditional": conditional})
    for name, hits in _wrapper_reads(src).items():
        reads.setdefault(name, []).extend(hits)
    for name, hits in _checkvar_reads(src).items():
        reads.setdefault(name, []).extend(hits)
    return reads


def _checkvar_reads(src: Source) -> dict:
    """Reads made with the raw netCDF API: `check_var(nfid,'NAME',vardesc,readvar)` resolves the
    variable and a following `nf90_get_var(nfid%fh, vardesc%varid, TARGET)` reads it.

    `GridMod.F90` reads the grid extents NHW, NHE, NVN, NVS this way; with only the `ncd_getvar`
    scans they were classified as never read and the graph called them inert (found 2026-10-15).
    The read is `conditional` unless a missing variable aborts (`endrun`) between the two calls."""
    out: dict = {}
    for path, no, text in src.grep(r"nf90_get_var *\(.*vardesc%varid", "-i", "-E"):
        lines = src.lines(path)
        back = [lines[k] for k in range(max(0, no - 9), no - 1)]
        names = [(i, re.search(r"check_var\s*\([^,]+,\s*'([A-Za-z0-9_]+)'", s, re.I))
                 for i, s in enumerate(back)]
        names = [(i, m.group(1)) for i, m in names if m]
        if not names:
            continue                      # generic helper: the name is a dummy argument
        i, name = names[-1]
        between = " ".join(back[i:])
        m = re.search(r"vardesc%varid\s*,\s*([A-Za-z_][\w%]*)", text, re.I)
        routine = enclosing_routine(lines, no)
        out.setdefault(name, []).append(
            {"file": path, "line": no, "routine": routine,
             "target": m.group(1).split("%")[-1] if m else None,
             "live": routine_is_referenced(src, routine),
             "conditional": not re.search(r"endrun", between, re.I), "via": "nf90_get_var"})
    return out


GETVAR_BY_ARG = re.compile(r"ncd_getvar\s*\(\s*([^,]+?)\s*,\s*([A-Za-z_]\w*)\s*,", re.I)


def _dummy_args(lines, routine: str) -> list[str]:
    """The dummy-argument names of `routine`, from its header (continuation lines joined)."""
    for i, s in enumerate(lines):
        m = ROUTINE_HDR.match(s)
        if m and m.group(1).lower() == routine.lower():
            hdr = s.split("!")[0]
            k = i + 1
            while hdr.rstrip().endswith("&") and k < len(lines):
                hdr = hdr.rstrip()[:-1] + " " + lines[k].split("!")[0].lstrip().lstrip("&")
                k += 1
            m2 = re.search(r"\(([^)]*)\)", hdr)
            return [a.strip().lower() for a in m2.group(1).split(",")] if m2 else []
    return []


def _wrapper_reads(src: Source) -> dict:
    """Reads that pass the file variable's NAME through a wrapper routine.

    `readimod.F90` reads the six bioaerosol fractions as `call read_aerosol_vars(loc,'fAeroDOM',
    fDOM)`, and the wrapper calls `ncd_getvar(grid_nfid,varname,loc,var_val)` after `check_var`.
    The name literal is at the CALL, not at `ncd_getvar`, so the literal-only scan above misses it
    and would classify a live, file-backed variable as never read. This finds every `ncd_getvar`
    whose name argument is one of its routine's dummy arguments, then every call of that routine
    passing a string literal in that position. Such a read is `conditional` when the wrapper asks
    `check_var` first (read if present, default otherwise)."""
    out: dict = {}
    for path, no, text in src.grep(r"ncd_getvar", "-i"):
        m = GETVAR_BY_ARG.search(text)
        if not m:
            continue
        lines = src.lines(path)
        wrapper = enclosing_routine(lines, no)
        if wrapper.startswith("<"):
            continue
        dummies = _dummy_args(lines, wrapper)
        arg = m.group(2).lower()
        if arg not in dummies:
            continue
        pos = dummies.index(arg)
        body = "\n".join(lines[max(0, no - 15):no])
        conditional = bool(re.search(rf"check_var\s*\([^)]*\b{arg}\b", body, re.I))
        for cpath, cno, ctext in src.grep(rf"call\s+{re.escape(wrapper)}\s*\(", "-i", "-E"):
            cm = re.search(rf"call\s+{re.escape(wrapper)}\s*\((.*)$", ctext.split("!")[0], re.I)
            if not cm:
                continue
            args = [a.strip() for a in cm.group(1).rstrip().rstrip(")").split(",")]
            if pos >= len(args):
                continue
            lit = re.fullmatch(r"'([A-Za-z0-9_]+)'", args[pos])
            if not lit:
                continue
            clines = src.lines(cpath)
            caller = enclosing_routine(clines, cno)
            tgt = re.match(r"([A-Za-z_][\w%]*)", args[-1]) if args else None
            out.setdefault(lit.group(1), []).append(
                {"file": cpath, "line": cno, "routine": caller,
                 "target": tgt.group(1).split("%")[-1] if tgt else None,
                 "live": routine_is_referenced(src, caller), "conditional": conditional,
                 "via": wrapper})
    return out


@functools.lru_cache(maxsize=None)
def _refs(src: Source, routine: str) -> tuple:
    return tuple(src.grep(rf"\b{re.escape(routine)}\b", "-i", "-E"))


def routine_is_referenced(src: Source, routine: str) -> bool:
    """True when anything other than the routine's own header/end/`public` line names it: a `call`,
    a function reference such as `.not.ReadPars()`, or a procedure binding. A read inside a routine
    nothing references is DEAD code, and a parameter read only there never reaches the model."""
    if routine.startswith("<"):
        return True
    for path, no, text in _refs(src, routine):
        t = text.split("!")[0]
        # a quoted string is not a reference: `subname='SecondaryGrowthZone'` is pasted into a
        # DIFFERENT routine at RootMod.F90:2287 and would otherwise keep a dead routine alive
        t = re.sub(r"'[^']*'|\"[^\"]*\"", "''", t)
        if not re.search(rf"\b{re.escape(routine)}\b", t, re.I):
            continue
        if ROUTINE_HDR.match(t) or ROUTINE_END.match(t) or re.match(r"\s*end\s+(subroutine|function)", t, re.I):
            continue
        if re.match(r"\s*(public|private)\b", t, re.I):
            continue
        return True
    return False


def tab_copies(src: Source, tabvar: str) -> list[dict]:
    """`X(...) = TABVAR(loc)` copies of a table-reader array into the per-PFT variable."""
    out = []
    pat = rf"=\s*{re.escape(tabvar)}\s*\("
    for path, no, text in src.grep(pat, "-i", "-E"):
        m = re.match(r"\s*([A-Za-z_][\w%]*)\s*(\(|=)", text)
        if m:
            out.append({"file": path, "line": no, "routine": enclosing_routine(src.lines(path), no),
                        "var": m.group(1).split("%")[-1]})
    return out


def aliases(src: Source, var: str) -> list[dict]:
    """`alias => obj%VAR` associations with a DIFFERENT local name, each scoped to its routine."""
    out = []
    pat = rf"\b[A-Za-z_]\w*\s*=>\s*([A-Za-z_]\w*%)*{re.escape(var)}\b"
    for path, no, text in src.grep(pat, "-i", "-E"):
        for m in re.finditer(rf"\b([A-Za-z_]\w*)\s*=>\s*(?:[A-Za-z_]\w*%)*{re.escape(var)}\b", text, re.I):
            alias = m.group(1)
            if alias.lower() != var.lower():
                lo, hi = routine_span(src.lines(path), no)
                out.append({"file": path, "line": no, "alias": alias, "span": [lo, hi],
                            "routine": enclosing_routine(src.lines(path), no)})
    return out


def classify(path: str, text: str, var: str) -> str:
    t = text.split("!")[0]
    if re.search(r"ncd_getvar", t, re.I):
        return "read"
    if re.search(r"=>\s*(?:[A-Za-z_]\w*%)*" + re.escape(var) + r"\b", t, re.I):
        return "alias"            # `associate(local => obj%Var)`: a name binding, not a use
    if os.path.basename(path) in IO_FILES:
        return "io"
    if re.search(r"writefix|write\s*\(", t, re.I):
        return "display"
    if "::" in t or ROUTINE_HDR.match(t) or re.match(r"\s*end\s+(subroutine|function)", t, re.I):
        return "decl"             # a declaration, or a routine header naming it as a dummy argument
    if re.search(r"\b(allocate|deallocate|destroy|call\s+destroy)\s*\(", t, re.I):
        return "alloc"
    if re.search(r"(^|%)\s*" + re.escape(var) + r"\b\s*(\([^=]*\))?\s*=[^=>]", t.strip(), re.I) and \
            re.match(r"\s*([A-Za-z_]\w*%)*" + re.escape(var) + r"\b", t, re.I):
        rhs = t.split("=", 1)[1]
        if re.fullmatch(r"\s*([A-Za-z_]\w*%)*" + re.escape(var) + r"\b\s*(\([^)]*\))?\s*", rhs, re.I):
            return "copy"
        return "assign"
    return "use"


def sites_of(src: Source, var: str) -> list[dict]:
    out, seen = [], set()
    for path, no, text in src.grep(var, "-i", "-w"):
        if not text.split("!")[0].strip() or not re.search(rf"\b{re.escape(var)}\b",
                                                             text.split("!")[0], re.I):
            continue   # a mention only inside a comment
        key = (path, no)
        if key in seen:
            continue
        seen.add(key)
        out.append({"file": path, "line": no, "routine": enclosing_routine(src.lines(path), no),
                    "kind": classify(path, text, var), "var": var, "text": text.strip()[:200]})
    for a in aliases(src, var):
        lines = src.lines(a["file"])
        lo, hi = a["span"]
        for i in range(lo, hi + 1):
            t = lines[i - 1].split("!")[0]
            if i != a["line"] and re.search(rf"\b{re.escape(a['alias'])}\b", t, re.I):
                key = (a["file"], i)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"file": a["file"], "line": i, "routine": enclosing_routine(lines, i),
                            "kind": classify(a["file"], lines[i - 1], a["alias"]), "var": a["alias"],
                            "alias_of": var, "text": lines[i - 1].strip()[:200]})
    for s_ in out:
        # A site inside a routine nothing calls (e.g. RootMod::SecondaryGrowthZone, whose only call
        # is commented out at cb243228) is not physics that runs.
        if s_["kind"] in ("use", "assign", "copy") and not routine_is_referenced(src, s_["routine"]):
            s_["kind"] = "dead"
    return sorted(out, key=lambda s: (s["file"], s["line"]))


@functools.lru_cache(maxsize=None)
def module_of(src: Source, path: str) -> str | None:
    for ln in src.lines(path):
        m = re.match(r"\s*module\s+(?!procedure\b)([A-Za-z_]\w*)", ln, re.I)
        if m:
            return m.group(1)
    return None


def uses_module(src: Source, path: str, mods: set) -> bool:
    if not mods:
        return False
    pat = re.compile(r"\s*use\s+(" + "|".join(re.escape(m) for m in mods) + r")\b", re.I)
    return any(pat.match(ln) for ln in src.lines(path))


def module_owners(src: Source, var: str) -> dict:
    """{file: module} for every MODULE-SCOPE declaration of `var` (a `::` line outside any routine).
    Derived-type components are excluded: a `%var` reference is unambiguous through its object."""
    out = {}
    for path, no, text in src.grep(rf"::.*\b{re.escape(var)}\b", "-i", "-E"):
        t = text.split("!")[0]
        if not re.search(rf"::.*\b{re.escape(var)}\b", t, re.I):
            continue
        lines = src.lines(path)
        if enclosing_routine(lines, no) != "<module scope>":
            continue
        # skip components declared inside a `type ... end type` block
        inside_type = False
        for i in range(no - 1, -1, -1):
            l = lines[i].strip().lower()
            if l.startswith("end type"):
                break
            if re.match(r"type\s*(,|::|\s)\s*\w", l) and not l.startswith("type("):
                inside_type = True
                break
        if not inside_type:
            out[path] = module_of(src, path) or "?"
    return out


_KEYWORDS = {"if", "elseif", "else", "do", "while", "where", "select", "case", "call", "return",
             "forall", "associate", "end", "then"}


def assigned_lhs(text: str) -> str | None:
    """The variable a Fortran statement assigns, or None. A one-line `IF (cond) X = ...` assigns X,
    not `IF`: the condition is stripped first (balanced parentheses), and a keyword is never an
    assignee. Until 2026-10-15 the bare pattern reported `IF` as a variable derived from BKDSI."""
    s = text.split("!")[0]
    m = re.match(r"\s*(?:else\s*)?if\s*\(", s, re.I)
    if m:
        depth, i = 1, m.end()
        while i < len(s) and depth:
            depth += {"(": 1, ")": -1}.get(s[i], 0)
            i += 1
        s = s[i:]
    m = re.match(r"\s*([A-Za-z_][\w%]*)\s*(\([^=]*\))?\s*=[^=>]", s)
    if not m:
        return None
    lhs = m.group(1).split("%")[-1]
    return None if lhs.lower() in _KEYWORDS else lhs


def resolve_param(src: Source, name: str, reads: dict) -> dict:
    entry = {"name": name, "reads": reads.get(name, []), "vars": [], "tab_copies": [], "sites": []}
    if not entry["reads"]:
        entry["status"] = "not-read"
        return entry
    vars_ = []
    for r in entry["reads"]:
        t = r["target"]
        if not t:
            continue
        if t.lower().endswith("_tab"):
            cps = tab_copies(src, t)
            entry["tab_copies"].extend(cps)
            vars_.extend(c["var"] for c in cps)
        else:
            vars_.append(t)
    entry["vars"] = sorted(set(vars_), key=str.lower)
    for v in entry["vars"]:
        sites = sites_of(src, v)
        owners = module_owners(src, v)
        if len(owners) > 1:
            # The SAME NAME is a module variable in more than one module (`VMXO` is both
            # NitroPars::VMXO, the file parameter, and PlantBGCPars::VMXO, nodule respiration).
            # A name grep conflates them; keep only sites in files that see the reading module.
            reader_files = {r["file"] for r in entry["reads"] if r["live"]} or {r["file"] for r in entry["reads"]}
            reader_mods = {m for f in reader_files for m in [module_of(src, f)] if m}
            keep = []
            for s_ in sites:
                if s_["file"] in reader_files or uses_module(src, s_["file"], reader_mods):
                    keep.append(s_)
            entry["name_collision"] = sorted(f"{m} ({f})" for f, m in owners.items())
            sites = keep
        entry["sites"].extend(sites)
    physics = [s for s in entry["sites"] if s["kind"] in ("use", "assign")]
    derived = set()
    for s in physics:
        lhs = assigned_lhs(s["text"])
        if lhs and lhs.lower() not in {v.lower() for v in entry["vars"]} and lhs.lower() != s["var"].lower():
            derived.add(lhs)
    entry["derived"] = sorted(derived, key=lambda v: (v.lower(), v))   # total order: reproducible
    live = [r for r in entry["reads"] if r["live"]]
    if not live:
        entry["status"] = "dead-read"          # read only inside routines nothing calls
    else:
        entry["status"] = "used" if physics else "read-not-used"
    entry["conditional"] = bool(live) and all(r["conditional"] for r in live)
    entry["routines"] = sorted({s["routine"] for s in physics})
    return entry


# ---------------------------------------------------------------------------------------------
# Citation resolution, shared by the validators (tools/check_ecosim_seed_citations.py,
# tools/check_ecosim_tested_params_in_kb.py). One grammar, so the seed and the wiki are held to
# the same standard:   [path/]File.F90:NNN[-MMM] (Routine)     the routine part is optional to
# PARSE and required where a checker says so.
# ---------------------------------------------------------------------------------------------
CITATION = re.compile(r"(?P<path>(?:[\w.-]+/)*(?P<file>[A-Za-z_][\w]*\.[Ff]90)):(?P<a>\d+)(?:-(?P<b>\d+))?"
                      r"(?:\s*\(\s*`?(?P<routine>[A-Za-z_]\w*)`?\s*\))?")


def find_citations(text: str) -> list[dict]:
    return [m.groupdict() for m in CITATION.finditer(text or "")]


def resolve_citation(src: "Source", cit: dict, expect: set | None = None) -> dict:
    """Check one citation at `src.commit`. Returns {ok, errors[], warnings[], file, routine_at}.

    errors:   the file does not exist (or a bare basename is ambiguous), a line is out of range,
              or a NAMED routine does not enclose the cited line(s).
    warnings: `expect` (variable names the cited code should mention) appears nowhere within two
              lines of the cited range -- a pointer that resolves but points at the wrong code.
    """
    out = {"ok": True, "errors": [], "warnings": [], "file": None, "routine_at": None}
    paths = src.resolve(cit["path"])
    if not paths:
        out["errors"].append(f"{cit['path']}: no such file at {src.commit}")
    elif len(paths) > 1:
        out["errors"].append(f"{cit['path']}: ambiguous basename at {src.commit} ({', '.join(paths)})")
    if out["errors"]:
        out["ok"] = False
        return out
    path = paths[0]
    out["file"] = path
    lines = src.lines(path)
    a = int(cit["a"]); b = int(cit["b"] or a)
    if a < 1 or b > len(lines) or b < a:
        out["errors"].append(f"{path}:{a}-{b}: out of range (file has {len(lines)} lines)")
        out["ok"] = False
        return out
    at = enclosing_routine(lines, a)
    out["routine_at"] = at
    if cit.get("routine"):
        named = cit["routine"].lower()
        inside = {enclosing_routine(lines, i).lower() for i in range(a, b + 1)}
        heads = {m.group(1).lower() for i in range(a, b + 1) for m in [ROUTINE_HDR.match(lines[i - 1])] if m}
        if named not in inside | heads:
            out["errors"].append(f"{path}:{a}{'-'+str(b) if b != a else ''}: cited routine "
                                 f"`{cit['routine']}` but the line is in `{at}`")
            out["ok"] = False
    if expect:
        window = " ".join(lines[max(0, a - 3):min(len(lines), b + 2)]).lower()
        if not any(re.search(rf"\b{re.escape(e.lower())}\b", window) for e in expect):
            out["warnings"].append(f"{path}:{a}: none of {sorted(expect)[:6]} appears within 2 lines")
    return out


def active_ecosim_profile(repo: Path, model_path=None) -> tuple[str, dict]:
    """(name, milestone) of the registered EcoSIM profile covering the commit in use, resolved by
    tools/kb_profile.py from the checkout at `model_path` / $A2MC_MODEL_PATH."""
    from tools.kb_profile import NoMatch, registry, resolve_or_default
    try:
        name = resolve_or_default("ecosim", model_path=model_path, repo=repo).profile
    except NoMatch as e:
        raise SystemExit(f"ERROR: {e}")
    return name, registry(repo)[name]


def param_names(paths: list[str]) -> list[str]:
    names = []
    for p in paths:
        rows = [ln for ln in open(p) if ln.strip() and not ln.lstrip().startswith("#")]
        for row in csv.DictReader(rows):
            n = (row.get("name") or "").strip()
            if n and n not in names:
                names.append(n)
    return names


def seed_param_names(seed_path: str) -> list[str]:
    import yaml
    return list((yaml.safe_load(open(seed_path)) or {}).get("parameters") or {})


def annotate_from_seed(data: dict, seed_path: str) -> dict:
    """Carry the curated seed's `inert: true` onto each entry. Static analysis sees a use site and
    calls the parameter used; the seed records the finding that the site cannot execute (CNRTLIG's
    only live use is in a lignification block whose C demand is zeroed first), and a page that
    reported only the static view would list a dead lever as live."""
    import yaml
    sp = (yaml.safe_load(open(seed_path)) or {}).get("parameters") or {}
    for n, e in data["params"].items():
        if (sp.get(n) or {}).get("inert"):
            e["seed_inert"] = (sp[n].get("calibration_notes") or "").strip()
    return data


def build(model_path: str, commit: str, names: list[str]) -> dict:
    src = Source(model_path, commit)
    reads = file_reads(src)
    return {"commit": src.full, "commit_short": src.full[:8], "n_names_read_at_commit": len(reads),
            "params": {n: resolve_param(src, n, reads) for n in names}}


def markdown(data: dict, provenance: list[str]) -> str:
    c = data["commit_short"]
    out = ["---",
           f"**Source pin:** EcoSIM commit `{c}`",
           "**Scope:** every source site that reads or uses a calibration parameter",
           "**Generated by:** `tools/ecosim_param_source_map.py` (do not edit by hand; regenerate)",
           "---", "",
           "# Calibration parameter source map",
           "",
           f"For each calibration parameter, this page lists where EcoSIM `{c}` reads it from the parameter file, "
           "the Fortran variable it lands in, and every physics site that uses that variable, each with its enclosing "
           "subroutine and `file:line`. It is generated from the source by `git grep`/`git show` at the pinned commit, so "
           "it cannot drift from the code; what each site MEANS is documented in the topic pages it links to "
           "(`plant_bgc/`, `microbial_bgc/`, `io_and_forcing/input_readers.md`).",
           "",
           "A read is marked **DEAD** when its enclosing routine is never called or referenced at this commit "
           "(`PlantInfoMod.F90` keeps an uncalled per-PFT reader beside the live table reader). "
           "Site kinds: **read** = the `ncd_getvar` call; **copy** = a plain copy into another data structure; "
           "**assign** = the variable is written by an expression (a derived value or an overwrite); **use** = the "
           "variable appears on the right-hand side of physics. Declarations, allocation, `associate` bindings, "
           "history/restart I/O, trait-display writes, and sites inside routines nothing calls (**dead**) are "
           "counted but not listed. Aliases from `associate(alias => obj%Var)` blocks are followed within "
           "their routine and marked `alias`.",
           "",
           "Parameters covered: " + ", ".join(
               (f"every entry of the curated seed `{p[5:]}`" if p.startswith("seed:") else f"`{p}`")
               for p in provenance) + ".", "",
           "## Summary", "",
           "| parameter | status | Fortran variable(s) | read in | physics routines |",
           "|---|---|---|---|---|"]
    for n, e in data["params"].items():
        rd = "; ".join(f"`{r['routine']}` ({r['file']}:{r['line']})" + ("" if r["live"] else " DEAD")
                       for r in e["reads"]) or "-"
        st = e["status"] + (" (seed: inert)" if e.get("seed_inert") else "")
        out.append(f"| `{n}` | {st} | {', '.join('`'+v+'`' for v in e['vars']) or '-'} | {rd} | "
                   f"{', '.join('`'+r+'`' for r in e.get('routines', [])) or '-'} |")
    for n, e in data["params"].items():
        out += ["", f"## `{n}`", ""]
        if e["status"] == "not-read":
            out.append(f"Not read by any name-literal `ncd_getvar` at `{c}`.")
            continue
        for r in e["reads"]:
            flag = "" if r["live"] else " -- **DEAD**: nothing calls this routine, so this read never happens"
            cond = " (read only if the variable is present: `check_var`)" if r["conditional"] else ""
            out.append(f"- **read** in `{r['routine']}` ({r['file']}:{r['line']}) into `{r['target']}`{cond}{flag}")
        for t in e["tab_copies"]:
            out.append(f"- **copy** table to per-PFT in `{t['routine']}` ({t['file']}:{t['line']}) into `{t['var']}`")
        hidden = {}
        rows = []
        for s in e["sites"]:
            if s["kind"] in ("decl", "io", "display", "read", "alloc", "alias", "dead"):
                hidden[s["kind"]] = hidden.get(s["kind"], 0) + 1
                continue
            al = f" (alias `{s['var']}`)" if s.get("alias_of") else ""
            code = s["text"][:140].replace("|", "\\|").replace("`", "'")
            rows.append(f"| {s['kind']} | `{s['routine']}` | {s['file']}:{s['line']} | `{code}`{al} |")
        if rows:
            out += ["", "| kind | routine | file:line | source line |", "|---|---|---|---|"] + rows
        if e.get("name_collision"):
            out += ["", "**Same name, different variables:** declared at module scope in " +
                    ", ".join(e["name_collision"]) + ". Sites are limited to files that use the module the "
                    "parameter is read into; a reference elsewhere is the OTHER variable."]
        if e.get("derived"):
            out += ["", "Variables computed from it (one hop): " + ", ".join(f"`{d}`" for d in e["derived"]) + "."]
        if e.get("seed_inert"):
            out += ["", "**Declared inert in the curated seed.** " + e["seed_inert"]]
        if e["status"] == "dead-read":
            out += ["", "**Not read on the live path at this commit**: every read sits in a routine nothing calls. "
                    "The sites listed are those of the VARIABLE, which a run fills by some other route, so they "
                    "are not effects of this parameter."]
        if e["status"] == "read-not-used":
            out += ["", "**Read but never used in physics at this commit** (no `use`/`assign` site)."]
        if hidden:
            out += ["", "Not listed: " + ", ".join(f"{v} {k}" for k, v in sorted(hidden.items())) + "."]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------------------------
# Outputs and mechanisms: the two companion reference pages. Both are generated, for the reason the
# parameter map is: `tools/yaml_wiki_validator.py` holds every curated mechanism and every output the
# seed names to appearing in the wiki, and a hand-maintained list would drift from the seed.
# ---------------------------------------------------------------------------------------------

def seed_output_names(seed: dict) -> list[str]:
    """Every output the seed references, collected exactly as yaml_wiki_validator's Dimension C does."""
    outs: set = set()
    for cat in (seed.get("categories") or {}).values():
        outs.update(cat.get("key_outputs") or [])
    for m in (seed.get("mechanisms") or {}).values():
        outs.update(m.get("affects") or [])
    outs.update((seed.get("outputs") or {}).keys())
    for p_ in (seed.get("parameters") or {}).values():
        outs.update(p_.get("affects") or [])
    return sorted(outs, key=lambda v: (v.lower(), v))


def _joined(lines, no: int) -> str:
    """Line `no` (1-based) with its Fortran continuation lines appended."""
    s, k = lines[no - 1].split("!")[0], no
    while s.rstrip().endswith("&") and k < len(lines):
        s = s.rstrip()[:-1] + " " + lines[k].split("!")[0].strip().lstrip("&")
        k += 1
    return s


def output_sites(src: Source, name: str) -> dict:
    """Where a history output is REGISTERED (`hist_addfld*(fname='NAME', ...)`) and where its buffer
    is FILLED (`this%<ptr>(...) = <rhs>`): the right-hand side names the model variable the tape
    reports, which is the link a diagnosis needs and the CDL does not carry."""
    entry = {"name": name, "registered": [], "filled": []}
    for path, no, _text in src.grep(rf"fname *= *'{re.escape(name)}'", "-E"):
        lines = src.lines(path)
        reg = _joined(lines, no)
        ptr = None
        for k in range(no - 1, max(0, no - 6), -1):
            m = re.search(r"data\w*_ptr\s*=>\s*this%(\w+)", lines[k - 1], re.I)
            if m:
                ptr = m.group(1)
                break
        units = re.search(r"units\s*=\s*'([^']*)'", reg)
        entry["registered"].append({"file": path, "line": no, "routine": enclosing_routine(lines, no),
                                    "ptr": ptr, "units": units.group(1) if units else ""})
        if not ptr:
            continue
        for fpath, fno, ftext in src.grep(rf"this%{re.escape(ptr)}\s*\(", "-i", "-E"):
            if "allocate" in ftext.lower() or "=>" in ftext:
                continue
            flines = src.lines(fpath)
            m = re.match(rf"\s*this%{re.escape(ptr)}\s*\([^=]*\)\s*=(?!=)(.*)$", _joined(flines, fno), re.I)
            if not m or m.group(1).strip().lower() in ("spval", "0._r8", "0.0_r8"):
                continue
            entry["filled"].append({"file": fpath, "line": fno, "routine": enclosing_routine(flines, fno),
                                    "rhs": " ".join(m.group(1).split())})
    return entry


def outputs_markdown(src: Source, seed: dict, seed_path: str) -> str:
    c = src.full[:8]
    names = seed_output_names(seed)
    rows, unregistered = [], []
    for n in names:
        e = output_sites(src, n)
        if not e["registered"]:
            unregistered.append(n)
            continue
        r = e["registered"][0]
        fills = "; ".join(f"`{f['file']}:{f['line']}` (`{f['routine']}`): `{f['rhs'][:140]}`" for f in e["filled"]) \
            or "no fill assignment found by pattern"
        rows.append(f"| `{n}` | {r['units']} | `{r['file']}:{r['line']}` (`{r['routine']}`) | {fills} |")
    out = ["---",
           f"**Source pin:** EcoSIM commit `{c}`",
           "**Scope:** every history output the curated seed names, and the model variable each one reports",
           "**Generated by:** `tools/ecosim_param_source_map.py --outputs-markdown` (do not edit by hand; regenerate)",
           "---", "",
           "# Curated output source map",
           "",
           f"Every output that `{seed_path}` names (a category's key outputs, a mechanism's or parameter's `affects`, the "
           "outputs block), with where EcoSIM registers it on the history tape and the assignment that fills its buffer. "
           "The right-hand side of that assignment is the model variable the tape reports, usually divided by the "
           "column area; read it before interpreting a tape value. Registered units are quoted from the registration "
           "call and can be wrong about the reduction (an hourly rate registered as a stock, for example); the topic "
           "pages say so where it matters.",
           "",
           f"Outputs covered: {len(names)}; registered at this commit: {len(rows)}.",
           "",
           "| output | registered units | registered at | filled at (routine): from |",
           "|---|---|---|---|",
           *rows]
    if unregistered:
        out += ["", "**Not registered at this commit:** " + ", ".join(f"`{n}`" for n in unregistered)]
    return "\n".join(out) + "\n"


def mechanisms_markdown(seed: dict, seed_path: str, commit_short: str) -> str:
    cats: dict = {}
    for cname, cat in (seed.get("categories") or {}).items():
        for m in cat.get("mechanisms") or []:
            cats.setdefault(m, []).append(cname)
    rows = []
    for name in sorted(seed.get("mechanisms") or {}, key=str.lower):
        m = seed["mechanisms"][name]
        doc = str(m.get("doc_reference") or "")
        page = doc.split("/", 1)[1] if "/" in doc else doc
        link = f"[`{page}`](../{page})" if page else "none"
        first = find_citations(str(m.get("code_reference") or ""))
        cite = f"`{first[0]['path']}:{first[0]['a']}` (`{first[0]['routine']}`)" if first else ""
        params = ", ".join(f"`{p_}`" for p_ in (m.get("parameters") or [])) or "none (no file parameter enters it)"
        rows.append(f"| `{name}` | {', '.join(cats.get(name, [])) or '-'} | {link} | {cite} | {params} |")
    return "\n".join([
        "---",
        f"**Source pin:** EcoSIM commit `{commit_short}`",
        "**Scope:** the knowledge graph's curated mechanisms and the wiki page that documents each",
        "**Generated by:** `tools/ecosim_param_source_map.py --mechanisms-markdown` (do not edit by hand; regenerate)",
        "---", "",
        "# Curated mechanism index",
        "",
        f"The mechanisms of `{seed_path}`, which are the `mechanism:` nodes of the knowledge graph, each with the wiki "
        "page that documents it, the first source line of its code reference, and the parameters the graph lets "
        "control it. Use it to move between a graph answer and the prose behind it.",
        "",
        "| mechanism | category | documented in | first code reference | parameters |",
        "|---|---|---|---|---|",
        *rows]) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-path", default=os.environ.get("A2MC_MODEL_PATH"))
    ap.add_argument("--commit", required=True)
    ap.add_argument("--param-list", action="append", default=[], help="CSV with a `name` column; repeatable")
    ap.add_argument("--param", action="append", default=[], help="one parameter name; repeatable")
    ap.add_argument("--seed", help="a curated seed YAML: cover every entry of its `parameters:` block "
                                   "(model-level, so a wiki page built this way names no case)")
    ap.add_argument("--json")
    ap.add_argument("--markdown")
    ap.add_argument("--outputs-markdown", help="with --seed: write the curated output source map")
    ap.add_argument("--mechanisms-markdown", help="with --seed: write the curated mechanism index")
    a = ap.parse_args()
    if not a.model_path:
        raise SystemExit("no --model-path and $A2MC_MODEL_PATH is unset")
    if a.outputs_markdown or a.mechanisms_markdown:
        if not a.seed:
            raise SystemExit("--outputs-markdown / --mechanisms-markdown need --seed")
        import yaml
        seed = yaml.safe_load(open(a.seed))
        src = Source(a.model_path, a.commit)
        rel = os.path.relpath(a.seed)
        if a.outputs_markdown:
            Path(a.outputs_markdown).write_text(outputs_markdown(src, seed, rel))
            print(f"wrote {a.outputs_markdown}")
        if a.mechanisms_markdown:
            Path(a.mechanisms_markdown).write_text(mechanisms_markdown(seed, rel, src.full[:8]))
            print(f"wrote {a.mechanisms_markdown}")
        if not (a.markdown or a.json):
            return 0
    names = (seed_param_names(a.seed) if a.seed else []) + param_names(a.param_list) + [n for n in a.param if n]
    names = list(dict.fromkeys(names))
    if not names:
        raise SystemExit("no parameters: pass --param-list and/or --param")
    data = build(a.model_path, a.commit, names)
    if a.seed:
        annotate_from_seed(data, a.seed)
    if a.json:
        Path(a.json).write_text(json.dumps(data, indent=1) + "\n")
    if a.markdown:
        prov = ([f"seed:{os.path.relpath(a.seed)}"] if a.seed else []) + \
            [os.path.relpath(p) for p in a.param_list] + [f"--param {n}" for n in a.param]
        Path(a.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(a.markdown).write_text(markdown(data, prov))
    bad = {n: e["status"] for n, e in data["params"].items() if e["status"] != "used"}
    print(f"{len(names)} parameters at {data['commit_short']}: "
          f"{sum(e['status'] == 'used' for e in data['params'].values())} used in physics; "
          f"not used: {bad or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
