#!/usr/bin/env python3
"""Report FILESYSTEM QUOTA and COMPUTE ALLOCATION headroom, and fail when a planned write won't fit.

WHY THIS EXISTS. Resource state is an INPUT to experiment design, not an environment property that
becomes interesting when it errors, so it should be one command and one exit code rather than a
traceback. Two properties make that worth a tool rather than a habit. A quota failure surfaces as an
error that reads nothing like a quota problem, from whichever write happens to be unlucky. And an
agent's own diagnostic output is typically captured to a file under the same filesystem, so a full
home degrades the ability to diagnose a full home, exactly when it is needed.

WHAT IT REFUSES TO DO. It never collapses "command not installed", "command timed out", "command
returned nothing" and "output did not parse" into a single 'unavailable'. Those have different causes
and different fixes, and treating the last three as the first is exactly the mistake that let the
2026-09-23 session conclude no quota tool existed when `myquota` runs in 0.3 s. Each is reported by
name, and any of them makes `--need-gb` fail CLOSED rather than pass silently.

IT WRITES NOTHING TO DISK, deliberately: a tool for diagnosing a full filesystem must work on one.

Usage:
    python3 tools/check_resources.py                 # report everything
    python3 tools/check_resources.py --need-gb 3     # assert 3 GiB of home headroom; non-zero if not
    python3 tools/check_resources.py --need-gb 3 --filesystem pscratch
    python3 tools/check_resources.py --json

Exit: 0 fine · 1 a threshold was crossed (warn, or --need-gb unmet) · 2 the state could not be read.

Author: Jing Tao with Claude
"""

import argparse
import json
import shutil
import subprocess
import sys

#: Warn below this fraction of a filesystem quota remaining, regardless of --need-gb.
WARN_FREE_FRAC = 0.10
#: Warn below this fraction of a compute allocation remaining.
WARN_ALLOC_FRAC = 0.10
#: Generous: `myquota` and `iris` each run in ~0.3-0.4 s, measured. A timeout this long means
#: something is genuinely wrong, not that the tool is slow -- so it is reported as a TIMEOUT and
#: never as an absence.
TIMEOUT_S = 60

_UNITS = {"KiB": 1 / 1048576, "MiB": 1 / 1024, "GiB": 1.0, "TiB": 1024.0, "PiB": 1048576.0,
          "K": 1 / 1048576, "M": 1 / 1024, "G": 1.0, "T": 1024.0}


def _to_gib(tok):
    """'39.05GiB' -> 39.05 (GiB). None when it does not parse -- never 0.0, which would read as empty."""
    tok = tok.strip()
    for suf, mult in sorted(_UNITS.items(), key=lambda kv: -len(kv[0])):
        if tok.endswith(suf):
            try:
                return float(tok[: -len(suf)]) * mult
            except ValueError:
                return None
    try:
        return float(tok)
    except ValueError:
        return None


def _run(cmd):
    """(status, text). status is one of: ok, absent, timeout, empty, error -- never merged."""
    if shutil.which(cmd[0]) is None:
        return "absent", f"{cmd[0]} is not on PATH"
    try:
        # 3.6-compatible: capture_output= and text= are 3.7+, and the SessionStart hook
        # invokes this with the system python3, which is 3.6 on this machine.
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return "timeout", f"{cmd[0]} exceeded {TIMEOUT_S}s (it normally takes under a second)"
    except OSError as e:
        return "error", f"{cmd[0]} failed to execute: {e}"
    out = (p.stdout or "").strip()
    if not out:
        return "empty", (f"{cmd[0]} exited {p.returncode} with NO stdout"
                         + (f"; stderr: {p.stderr.strip()[:200]}" if p.stderr.strip() else "")
                         + ". NOTE: an empty answer is not 'no such tool' -- on a FULL filesystem"
                           " output capture itself can fail, which is when you most need this.")
    return "ok", out


def read_quota():
    status, text = _run(["myquota"])
    if status != "ok":
        return {"status": status, "detail": text, "rows": {}}
    rows = {}
    for line in text.splitlines()[1:]:
        f = line.split()
        if len(f) < 4:
            continue
        used, quota = _to_gib(f[1]), _to_gib(f[2])
        if used is None or quota is None or quota <= 0:
            continue
        rows[f[0]] = {"used_gib": used, "quota_gib": quota, "free_gib": quota - used,
                      "used_frac": used / quota}
    return {"status": "ok" if rows else "error",
            "detail": "" if rows else "myquota produced output but no row parsed", "rows": rows}


def read_alloc():
    status, text = _run(["iris"])
    if status != "ok":
        return {"status": status, "detail": text, "rows": {}}
    rows = {}
    for line in text.splitlines():
        f = line.split()
        if len(f) < 5 or f[0].lower().startswith(("project", "---")):
            continue
        try:
            charged, allocated = float(f[3]), float(f[4])
        except ValueError:
            continue
        rows[f[0]] = {"charged": charged, "allocated": allocated,
                      "free": allocated - charged,
                      "free_frac": (allocated - charged) / allocated if allocated > 0 else 0.0}
    return {"status": "ok" if rows else "error",
            "detail": "" if rows else "iris produced output but no row parsed", "rows": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--need-gb", type=float, default=None,
                    help="assert this many GiB are free on --filesystem; exit non-zero otherwise")
    ap.add_argument("--filesystem", default="home", help="which quota row --need-gb applies to")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="print only problems")
    a = ap.parse_args()

    q, al = read_quota(), read_alloc()
    rc = 0

    if a.json:
        print(json.dumps({"quota": q, "allocation": al}, indent=2))
    else:
        if q["status"] != "ok":
            print(f"  QUOTA UNREADABLE [{q['status']}]: {q['detail']}")
            rc = max(rc, 2)
        else:
            for name, r in q["rows"].items():
                flag = "  " if r["used_frac"] < 1 - WARN_FREE_FRAC else "!!"
                if flag == "!!":
                    rc = max(rc, 1)
                if not a.quiet or flag == "!!":
                    print(f"{flag} {name:<10} {r['used_gib']:9.2f} / {r['quota_gib']:9.2f} GiB"
                          f"   {r['used_frac']:6.1%} used   {r['free_gib']:9.2f} GiB free")
        if al["status"] != "ok":
            print(f"  ALLOCATION UNREADABLE [{al['status']}]: {al['detail']}")
            rc = max(rc, 2)
        else:
            for name, r in al["rows"].items():
                if r["allocated"] <= 0:
                    if not a.quiet:
                        print(f"   {name:<10} NO ALLOCATION (0 hours) -- jobs here will not run")
                    continue
                flag = "  " if r["free_frac"] > WARN_ALLOC_FRAC else "!!"
                if flag == "!!":
                    rc = max(rc, 1)
                if not a.quiet or flag == "!!":
                    print(f"{flag} {name:<10} {r['charged']:10.1f} / {r['allocated']:10.1f} hours"
                          f"   {r['free_frac']:6.1%} free")

    if a.need_gb is not None:
        # AN EXPLICIT ASSERTION OWNS THE EXIT CODE. The advisory warnings above must not leak into
        # it: a caller asking "can I write N GiB to pscratch" gets an answer about pscratch, and a
        # separate warning that HOME is nearly full is not a reason to refuse that write. Measured
        # while testing this tool -- the first version returned 1 on a request it had just approved.
        row = q["rows"].get(a.filesystem)
        if row is None:
            # FAIL CLOSED, and say WHICH failure. "the quota tool broke" and "that filesystem is not
            # in the report" have different fixes, and reporting the tool's status for a missing row
            # printed the useless 'Reason: ok'.
            if q["status"] != "ok":
                why = "the quota tool did not answer [%s]: %s" % (q["status"], q["detail"])
            else:
                why = ("the quota report parsed, but has no row named '%s'. Rows present: %s"
                       % (a.filesystem, ", ".join(sorted(q["rows"])) or "(none)"))
            print("\n  REFUSING: %.2f GiB on '%s' cannot be confirmed available -- %s"
                  % (a.need_gb, a.filesystem, why))
            return 2
        ok = row["free_gib"] >= a.need_gb
        print("\n  %s: need %.2f GiB on %s, %.2f GiB free%s"
              % ("OK" if ok else "INSUFFICIENT", a.need_gb, a.filesystem, row["free_gib"],
                 "" if ok else (" -- short by %.2f GiB. Write to CFS or scratch instead."
                                % (a.need_gb - row["free_gib"]))))
        return 0 if ok else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
