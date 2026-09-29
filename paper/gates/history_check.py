"""Check the corrected disposition count against each object's full GCAT phase history.

A reviewer objected that the corrected classifier places C (collided) in DESTROYED,
although GCAT's status definitions allow an object to survive a collision and enter
another phase. Checking that needs the object's history, and the four GCAT files the
pipeline ingests do not hold it: each carries exactly one record per object. GCAT's
catalogue index says where the rest lives:

    ecat        Event Catalog   Later phases in history for objects in primary catalogs.
    currentcat  Summary catalog Most recent phase for each S and A object.

This script appends each object's ecat phases to its first-phase record, takes the
latest phase as GCAT's current account of the object, resolves docked, grappled,
attached and transferred objects through the object they joined, and recomputes the
disposition comparison against CelesTrak.

Inputs:
  data/celestrak_satcat.csv, data/gcat_*.tsv   the frozen 18 Aug 2026 files the paper uses
  data/gcat_ecat_20260928.tsv                  GCAT ecat, data update of 28 Sep 2026

The ecat file postdates the frozen data by six weeks and no August copy could be
obtained, so ecat phases starting after 18 Aug 2026 are dropped. Corrections GCAT made
to older phases in that window cannot be separated out and are a stated limitation.

Status semantics follow planet4589.org/space/gcat/web/intro/phases.html:
  C  "the collision can result in the destruction of the object, in which case there
      is no subsequent phase; or the object can survive, in which case t2 starts a new
      phase."  So C is destruction only when it is the last phase.
  E  "free in orbit until breakup at t2. Next phase of this object is a debris
      fragment."  So E is a phase boundary, not a disposition. When no successor phase
      is recorded the object's current state is unrecorded, and it is reported
      separately rather than silently assigned.

Run: python3 paper/gates/history_check.py
Writes: paper/gates/history_results.json
"""
import collections
import datetime as dt
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from reconcile import (load_celestrak, load_gcat, norm_status, DESTROYED, TRANSITION,  # noqa: E402
                       INORBIT, LEFT_EARTH, ERROR)

FREEZE = dt.date(2026, 8, 18)
ECAT = ROOT / "data" / "gcat_ecat_20260928.tsv"
MAIN = ["gcat_satcat.tsv", "gcat_auxcat.tsv", "gcat_ftocat.tsv", "gcat_satcat100k.tsv"]

# Latest-phase semantics. C is terminal only as a last phase, which is the only place
# this table is consulted.
GONE_LAST = {"R", "D", "L", "LF", "S", "F", "AF", "AS", "AR", "AR IN", "AL", "AL IN",
             "TX", "C"}
FREE_LAST = {"O", "AO", "AO IN", "OX", "UDK", "REL", "DEP"}
JOINED_LAST = {"DK", "GRP", "ATT", "TFR", "TFR E", "TFR IN"}   # resolve through Dest
UNRECORDED_LAST = {"E", "N", "NA", "LEASE", "EVA DP", "EVA RP", "REFLT", "TO", "TOA",
                   "ALO"}

MONTHS = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def vague_date(s):
    """Parse the leading 'YYYY Mon DD' of a GCAT vague date; None if absent."""
    m = re.match(r"\s*(\d{4})(?:\s+([A-Z][a-z]{2}))?(?:\s+(\d{1,2}))?", s or "")
    if not m or not m.group(1):
        return None
    y = int(m.group(1))
    mo = MONTHS.get(m.group(2) or "Jan", 1)
    d = int(m.group(3) or 1)
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return dt.date(y, mo, 1)


def load_tsv(path):
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        hdr = [h.strip() for h in f.readline().lstrip("#").rstrip("\n").split("\t")]
        for line in f:
            if line.startswith("#"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < len(hdr):
                continue
            out.append(dict(zip(hdr, [x.strip() for x in p])))
    return out


def build_histories():
    """JCAT -> ordered list of phase records (first-phase record, then ecat phases)."""
    hist = {}
    for name in MAIN:
        _, rows, _ = load_gcat(name)
        for r in rows:
            hist.setdefault(r["JCAT"], []).append(r)
    dropped = 0
    for r in load_tsv(ECAT):
        sd = vague_date(r.get("SDate", ""))
        if sd is not None and sd > FREEZE:
            dropped += 1
            continue
        hist.setdefault(r["JCAT"], []).append(r)
    return hist, dropped


def disposition(jcat, hist, seen=None):
    """Return (kind, last_status, chain). kind is gone | inorbit | left | error |
    unrecorded | unknown."""
    seen = seen or []
    if jcat in seen or len(seen) > 20:
        return "unknown", None, seen
    phases = hist.get(jcat)
    if not phases:
        return "unknown", None, seen + [jcat]
    s = norm_status(phases[-1].get("Status", ""))
    chain = seen + [f"{jcat}:{s}"]
    if s in ERROR:
        return "error", s, chain
    if s in GONE_LAST:
        return "gone", s, chain
    if s in FREE_LAST:
        return "inorbit", s, chain
    if s in LEFT_EARTH:
        return "left", s, chain
    if s in JOINED_LAST:
        dest = phases[-1].get("Dest", "").split("/")[0].strip()
        if not dest or dest == "-":
            return "unknown", s, chain
        kind, _, c2 = disposition(dest, hist, chain)
        return kind, s, c2
    if s in UNRECORDED_LAST:
        return "unrecorded", s, chain
    return "unknown", s, chain


def main():
    ct = load_celestrak()
    sat, _, _ = load_gcat("gcat_satcat.tsv")
    hist, dropped = build_histories()
    both = sorted(set(ct) & set(sat), key=int)
    ctdec = {n for n in both if ct[n]["DECAY_DATE"].strip()}

    # The published corrected classifier (pooled first-phase status sets).
    st = {n: {norm_status(p.get("Status", "")) for p in sat[n]} for n in both}
    claims = {n for n in both if (st[n] & (DESTROYED | INORBIT | LEFT_EARTH))
              and not (st[n] & ERROR)}
    gone_v1 = {n for n in claims if st[n] & DESTROYED}
    inorb_v1 = {n for n in claims if (st[n] & INORBIT) and not (st[n] & DESTROYED)
                and not (st[n] & LEFT_EARTH)}
    v1 = (gone_v1 - ctdec) | (inorb_v1 & ctdec)

    # Full-history classifier. Identifier collisions (several JCATs on one number)
    # are resolved on every JCAT; the object counts as disagreeing only if all agree.
    kinds, detail = {}, {}
    for n in both:
        ks = {(k, s, tuple(c)) for k, s, c in
              (disposition(r["JCAT"], hist) for r in sat[n])}
        kset = {k for k, _, _ in ks}
        kinds[n] = kset.pop() if len(kset) == 1 else "ambiguous"
        detail[n] = sorted((k, s or "", "->".join(c)) for k, s, c in ks)
    gone_v2 = {n for n in both if kinds[n] == "gone"}
    inorb_v2 = {n for n in both if kinds[n] == "inorbit"}
    v2 = (gone_v2 - ctdec) | (inorb_v2 & ctdec)
    unrec = {n for n in both if kinds[n] == "unrecorded"}

    # Sensitivity: an E with no recorded successor counted as destroyed (the reading
    # the published correction used) instead of set aside.
    e_unrec = {n for n in unrec
               if norm_status(hist[sat[n][0]["JCAT"]][-1].get("Status", "")) == "E"}
    v2_e_gone = v2 | (e_unrec - ctdec)

    first = {n: norm_status(sat[n][0].get("Status", "")) for n in both}
    moved_out = sorted(v1 - v2, key=int)
    moved_in = sorted(v2 - v1, key=int)

    def grp(ns):
        return dict(collections.Counter(
            f"{first[n]}|{ct[n]['ORBIT_TYPE'].strip()}" for n in ns).most_common())

    res = {
        "freeze_date": FREEZE.isoformat(),
        "ecat_file": ECAT.name,
        "ecat_phases_dropped_after_freeze": dropped,
        "shared_objects": len(both),
        "published_corrected_count_v1": len(v1),
        "full_history_count_v2": len(v2),
        "full_history_count_if_unsucceeded_E_is_destroyed": len(v2_e_gone),
        "kinds": dict(collections.Counter(kinds.values())),
        "unrecorded_by_last_status": dict(collections.Counter(
            norm_status(hist[sat[n][0]["JCAT"]][-1].get("Status", "")) for n in unrec)),
        "v1_only_count": len(moved_out),
        "v2_only_count": len(moved_in),
        "v1_only_by_first_status_and_ct_orbit_type": grp(moved_out),
        "v2_only_by_first_status_and_ct_orbit_type": grp(moved_in),
        "v2_by_first_status_and_ct_orbit_type": grp(v2),
        "v1_residue_C_E_objects": {
            n: {"name": ct[n]["OBJECT_NAME"], "ct_decay": ct[n]["DECAY_DATE"],
                "ct_orbit_type": ct[n]["ORBIT_TYPE"], "history": detail[n],
                "in_v2": n in v2}
            for n in sorted(v1, key=int) if first[n] in ("C", "E")},
        "v2_only_examples": {
            n: {"name": ct[n]["OBJECT_NAME"], "ct_decay": ct[n]["DECAY_DATE"],
                "ct_orbit_type": ct[n]["ORBIT_TYPE"], "history": detail[n]}
            for n in moved_in[:40]},
    }
    (HERE / "history_results.json").write_text(json.dumps(res, indent=2))
    for k in ("shared_objects", "published_corrected_count_v1", "full_history_count_v2",
              "full_history_count_if_unsucceeded_E_is_destroyed", "kinds",
              "unrecorded_by_last_status", "ecat_phases_dropped_after_freeze",
              "v1_only_count", "v2_only_count", "v1_only_by_first_status_and_ct_orbit_type",
              "v2_only_by_first_status_and_ct_orbit_type",
              "v2_by_first_status_and_ct_orbit_type"):
        print(f"{k}: {res[k]}")


if __name__ == "__main__":
    main()
