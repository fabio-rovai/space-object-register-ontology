"""Label generated verification paths by what they compute, not by what they contain.

The original trials were labelled by pattern matching over the generated source. A
reviewer asked for the labels to be validated against the code's behaviour. This
module executes each generated path on a synthetic probe catalogue and decodes which
(status code, CelesTrak state) cells it counts as disagreements.

Probe design. Each cell is a GCAT status code paired with whether CelesTrak carries a
decay date. Cell i holds 2**i objects, so any count a path returns is a sum of
distinct powers of two and decodes to exactly the set of cells it counted. Two cells
are controls that every reading counts: R against no decay date (GCAT gone, CelesTrak
silent) and O against a decay date (GCAT in orbit, CelesTrak decayed).

The generated code runs in a scratch directory holding the probe files under the
paths the prompt names, with the prompt's own module (pre-correction constants and
loaders) importable as `reconcile` and preloaded into the namespace, because many
paths reference those names without importing them. `python_side` is stubbed to
return a sentinel that decodes to nothing, so the original path's number can never be
mistaken for the generated one.

Usage: from behaviour_probe import probe; probe(code_string) -> dict
"""
import contextlib
import csv
import io
import multiprocessing as mp
import os
import pathlib
import re
import sys
import tempfile
import textwrap
import types

CODES = ["E", "C", "DK", "ATT", "TFR", "GRP"]
CELLS = [(c, dec) for c in CODES for dec in (True, False)] + [("R", False), ("O", True)]
CONTROL_BITS = {12, 13}
SENTINEL = 10 ** 9 + 7
DEFECT_SIGNATURE = frozenset(  # what the pre-correction code counts
    [i for i, (c, dec) in enumerate(CELLS) if c in CODES and dec] + [12, 13])

CT_HEADER = ("OBJECT_NAME,OBJECT_ID,NORAD_CAT_ID,OBJECT_TYPE,OPS_STATUS_CODE,OWNER,"
             "LAUNCH_DATE,LAUNCH_SITE,DECAY_DATE,PERIOD,INCLINATION,APOGEE,PERIGEE,RCS,"
             "DATA_STATUS_CODE,ORBIT_CENTER,ORBIT_TYPE").split(",")
GCAT_HEADER = ("JCAT Satcat Launch_Tag Piece Type Name PLName LDate Parent SDate Primary "
               "DDate Status Dest Owner State").split()

RECONCILE_STUB = '''
import csv, collections, pathlib
csv.field_size_limit(10_000_000)
ROOT = pathlib.Path(".").resolve()   # the prompt's module defines ROOT and DATA
DATA = ROOT / "data"
GONE = {"R","D","L","LF","S","F","AF","AS","AR","AR IN","AL","AL IN","TX"}
INORBIT = {"O","AO","AO IN","OX"}
LEFT_EARTH = {"DSO","DSA","DSA IN","EO","EAO","EN","OI","OE","LO","LOA"}
ERROR = {"ERR"}
LOST = {"OX"}

def load_celestrak():
    out = {}
    with open(DATA/"celestrak_satcat.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["NORAD_CAT_ID"].strip()] = r
    return out

def load_gcat(name):
    by_norad = collections.defaultdict(list)
    rows, nona = [], []
    with open(DATA/name, encoding="utf-8") as f:
        hdr = [h.strip() for h in f.readline().lstrip("#").rstrip("\\n").split("\\t")]
        for line in f:
            if line.startswith("#"):
                continue
            p = line.rstrip("\\n").split("\\t")
            if len(p) < len(hdr):
                continue
            r = dict(zip(hdr, [x.strip() for x in p]))
            rows.append(r)
            s = r.get("Satcat", "")
            if s.isdigit():
                by_norad[str(int(s))].append(r)
            else:
                nona.append(r)
    return by_norad, rows, nona

def statuses(phases):
    return {p.get("Status","").strip() for p in phases}
'''

GOVERNANCE_STUB = f'''
from reconcile import *
def python_side():
    return {{"DispositionDisagreement": {SENTINEL}}}
'''


def write_probe(root):
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    ct_rows, g_rows = [], []
    norad = 20000   # five digits: GCAT pads to five, CelesTrak does not
    for i, (code, decayed) in enumerate(CELLS):
        for _ in range(2 ** i):
            norad += 1
            ct_rows.append({
                "OBJECT_NAME": f"PROBE {norad}", "OBJECT_ID": f"2000-{norad % 1000:03d}A",
                "NORAD_CAT_ID": str(norad), "OBJECT_TYPE": "PAY", "OPS_STATUS_CODE": "",
                "OWNER": "US", "LAUNCH_DATE": "2000-01-01", "LAUNCH_SITE": "AFETR",
                "DECAY_DATE": "2001-01-01" if decayed else "", "PERIOD": "95.0",
                "INCLINATION": "51.6", "APOGEE": "420", "PERIGEE": "410", "RCS": "1.0",
                "DATA_STATUS_CODE": "", "ORBIT_CENTER": "EA",
                "ORBIT_TYPE": "IMP" if decayed else "ORB"})
            g_rows.append([f"S{norad:05d}", f"{norad:05d}", "2000-001", "A", "P",
                           f"Probe {norad}", "-", "2000 Jan  1", "S00001", "2000 Jan  1",
                           "Earth", "-" if code == "O" else "2000 Jun  1", code,
                           "S00002" if code in ("DK", "GRP", "ATT", "TFR", "C") else "-",
                           "NASA", "US"])
    with open(data / "celestrak_satcat.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CT_HEADER)
        w.writeheader()
        w.writerows(ct_rows)
    with open(data / "gcat_satcat.tsv", "w", encoding="utf-8") as f:
        f.write("#" + "\t".join(GCAT_HEADER) + "\n")
        for r in g_rows:
            f.write("\t".join(r) + "\n")
    # the other GCAT files some paths open; empty but well formed
    for name in ("gcat_auxcat.tsv", "gcat_ftocat.tsv", "gcat_satcat100k.tsv"):
        with open(data / name, "w", encoding="utf-8") as f:
            f.write("#" + "\t".join(GCAT_HEADER) + "\n")
    (root / "reconcile.py").write_text(RECONCILE_STUB)
    (root / "governance_report.py").write_text(GOVERNANCE_STUB)
    pl = root / "pipeline"
    pl.mkdir(exist_ok=True)
    (pl / "reconcile.py").write_text(RECONCILE_STUB)
    (pl / "governance_report.py").write_text(GOVERNANCE_STUB)


def decode(x):
    if not isinstance(x, int) or isinstance(x, bool) or x < 0 or x >= 2 ** len(CELLS):
        return None
    return frozenset(i for i in range(len(CELLS)) if x >> i & 1)


def strip_fences(t):
    m = re.findall(r"```(?:python|py)?\n(.*?)```", t, re.S)
    return "\n\n".join(m) if m else t


def _ints(v, depth=0):
    if depth > 3:
        return
    if isinstance(v, bool):
        return
    if isinstance(v, int):
        yield v
    elif isinstance(v, (set, frozenset, list, tuple)):
        if isinstance(v, (set, frozenset)) and v and all(isinstance(e, str) for e in v):
            yield len(v)
        else:
            for e in v:
                yield from _ints(e, depth + 1)
    elif isinstance(v, dict):
        for k, e in v.items():
            yield from _ints(e, depth + 1)


def _binders(reconcile):
    """Supply the arguments a verification function most plausibly expects."""
    return {
        "celestrak": reconcile.load_celestrak, "ct": reconcile.load_celestrak,
        "sat": lambda: reconcile.load_gcat("gcat_satcat.tsv")[0],
        "gcat": lambda: reconcile.load_gcat("gcat_satcat.tsv")[0],
        "data_dir": lambda: pathlib.Path("data"), "datadir": lambda: pathlib.Path("data"),
        "root": lambda: pathlib.Path("."),
    }


def _headline(r):
    """The single number a path reports: an int, the Disposition entry of a dict,
    the size of a set of identifiers, or the first int of a tuple."""
    if isinstance(r, bool):
        return None
    if isinstance(r, int):
        return r
    if isinstance(r, dict):
        for k, v in r.items():
            if "dispos" in str(k).lower() and isinstance(v, int):
                return v
        ints = [v for v in r.values() if isinstance(v, int) and not isinstance(v, bool)]
        return ints[0] if len(ints) == 1 else None
    if isinstance(r, (set, frozenset)):
        return len(r)
    if isinstance(r, (tuple, list)) and r:
        return _headline(r[0])
    return None


def _run(code, root, q):
    os.chdir(root)
    sys.argv = ["generated_check.py"]   # command-line paths must not see harness args
    sys.path[:0] = [str(root), str(root / "pipeline")]
    import reconcile  # the stub
    ns = {"__name__": "__generated__", "__builtins__": __builtins__,
          "__file__": str(root / "pipeline" / "generated_check.py")}
    ns.update({k: getattr(reconcile, k) for k in dir(reconcile) if not k.startswith("__")})
    ns["python_side"] = lambda: {"DispositionDisagreement": SENTINEL}
    out = {"exec_error": None, "calls": []}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<generated>", "exec"), ns)
    except SystemExit:
        pass
    except BaseException as e:  # noqa: BLE001
        out["exec_error"] = f"{type(e).__name__}: {e}"[:300]
    fns = [(k, v) for k, v in ns.items() if isinstance(v, types.FunctionType)
           and getattr(v.__code__, "co_filename", "") == "<generated>"]
    for name, fn in fns:
        if re.match(r"_?(read|load|parse|classify|norm|get)_?", name):
            continue            # helpers, not the verification path
        nreq = fn.__code__.co_argcount - len(fn.__defaults__ or ())
        args = []
        if nreq:
            names = fn.__code__.co_varnames[:nreq]
            binder = _binders(reconcile)
            if not all(any(k in a.lower() for k in binder) for a in names):
                out["calls"].append({"fn": name, "skipped": f"needs arguments {names}"})
                continue
            args = [next(v() for k, v in binder.items() if k in a.lower()) for a in names]
        b2 = io.StringIO()
        try:
            with contextlib.redirect_stdout(b2):
                r = fn(*args)
            vals = list(_ints(r))
            printed = [int(s) for s in re.findall(r"(?<![\w.])\d+(?![\w.])", b2.getvalue())]
            out["calls"].append({"fn": name, "returned": vals[:20], "printed": printed[:40],
                                 "headline": _headline(r)})
        except SystemExit as e:
            printed = [int(s) for s in re.findall(r"(?<![\w.])\d+(?![\w.])", b2.getvalue())]
            out["calls"].append({"fn": name, "exit": str(e)[:100], "printed": printed[:40]})
        except BaseException as e:  # noqa: BLE001
            out["calls"].append({"fn": name, "error": f"{type(e).__name__}: {e}"[:200]})
    q.put(out)


def probe(text, timeout=60):
    code = strip_fences(text)
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        write_probe(root)
        q = mp.Queue()
        p = mp.Process(target=_run, args=(code, root, q))
        p.start()
        p.join(timeout)
        if p.is_alive():
            p.terminate()
            return {"status": "timeout"}
        raw = q.get() if not q.empty() else {"exec_error": "no result", "calls": []}
    # Candidate numbers: returned values first, printed values as a fallback.
    sigs = {}
    for c in raw["calls"]:
        for src in ("returned", "printed"):
            for v in c.get(src, []):
                s = decode(v)
                if (s is not None and CONTROL_BITS <= s and v != SENTINEL
                        and v != 2 ** len(CELLS) - 1):
                    sigs.setdefault(s, set()).add((c["fn"], src))
    if not sigs:
        ran = any("returned" in c or "printed" in c for c in raw["calls"])
        status = "does not run" if (raw["exec_error"] or not ran) else "runs, no decodable count"
        return {"status": status, "raw": raw}
    if len(sigs) > 1:
        # several functions returning different counts: prefer the one that is not
        # a re-implementation of the original, else report ambiguity
        non_defect = [s for s in sigs if s != DEFECT_SIGNATURE]
        chosen = non_defect[0] if len(non_defect) == 1 else None
        if chosen is None:
            return {"status": "ambiguous", "signatures": [sorted(s) for s in sigs], "raw": raw}
    else:
        chosen = next(iter(sigs))
    return {"status": "ok", "signature": sorted(chosen), **describe(chosen),
            "source_fns": sorted({f for f, _ in sigs[chosen]}), "raw": raw}


REAL_DATA = pathlib.Path(__file__).resolve().parent.parent.parent / "data"


def real_count(text, fns, timeout=900):
    """Run the same code on the frozen 18 Aug 2026 catalogue files and return the
    headline number each named function reports: the number the gate would have seen."""
    code = strip_fences(text)
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        write_probe(root)
        for f in (root / "data").iterdir():
            f.unlink()
        for f in REAL_DATA.glob("*"):
            (root / "data" / f.name).symlink_to(f)
        q = mp.Queue()
        p = mp.Process(target=_run, args=(code, root, q))
        p.start()
        p.join(timeout)
        if p.is_alive():
            p.terminate()
            return {"status": "timeout"}
        raw = q.get() if not q.empty() else {"exec_error": "no result", "calls": []}
    return {c["fn"]: c.get("headline", c.get("error") or c.get("exit"))
            for c in raw["calls"] if c["fn"] in fns}


def describe(sig):
    counted = {CELLS[i] for i in sig}
    per_code = {}
    for c in CODES:
        dec, nodec = (c, True) in counted, (c, False) in counted
        per_code[c] = ("in orbit" if dec and not nodec else
                       "gone" if nodec and not dec else
                       "excluded" if not dec and not nodec else "both")
    inherits = sig == DEFECT_SIGNATURE
    h1_fixed = per_code["E"] != "in orbit" or per_code["C"] != "in orbit"
    h2_fixed = any(per_code[c] != "in orbit" for c in ("DK", "ATT", "TFR", "GRP"))
    return {"per_code": per_code, "inherits_defect_behaviourally": inherits,
            "fixes_H1": h1_fixed, "fixes_H2": h2_fixed}


if __name__ == "__main__":
    import json
    for f in sys.argv[1:]:
        r = probe(pathlib.Path(f).read_text())
        r.pop("raw", None)
        print(f, json.dumps(r))
