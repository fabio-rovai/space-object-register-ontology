"""Object-level ledger for the disposition count: 932 -> 261 -> 220.

A reviewer could not reconcile two pairs of figures in the paper: 998 "spurious
disagreements" against an original total of 932, and 769 docking or attachment cases
against 500. Both came from mixing counting units. This script tracks every object
through the three versions of the count, so that each figure the paper states is a
set size produced here, with its unit named.

  v0  published first run       pre-correction constants (git 24d684e)
  v1  first correction          current pipeline/reconcile.py (commit 60d2938)
  v2  full-history check        paper/gates/history_check.py

Run: python3 paper/gates/count_ledger.py
Writes: paper/gates/count_ledger.json
"""
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "pipeline"))
import history_check as H  # noqa: E402
from evaluate_gates import GONE_PRE  # noqa: E402
from reconcile import (load_celestrak, load_gcat, norm_status, DESTROYED,  # noqa: E402
                       TRANSITION, INORBIT, LEFT_EARTH, ERROR)


def main():
    ct = load_celestrak()
    sat, _, _ = load_gcat("gcat_satcat.tsv")
    both = {n for n in sat if n in ct}
    ctdec = {n for n in both if ct[n]["DECAY_DATE"].strip()}

    # v0, verbatim logic of git 24d684e (strip only, no '?' normalisation).
    st0 = {n: {p.get("Status", "").strip() for p in sat[n]} for n in both}
    gone0 = {n for n in both if st0[n] & GONE_PRE}
    v0_gone_ct_silent = gone0 - ctdec
    v0_ct_decayed_not_gone = {n for n in both if n in ctdec and n not in gone0
                              and not (st0[n] & LEFT_EARTH)}
    v0 = v0_gone_ct_silent | v0_ct_decayed_not_gone

    # v1, current pipeline.
    st = {n: {norm_status(p.get("Status", "")) for p in sat[n]} for n in both}
    claims = {n for n in both if (st[n] & (DESTROYED | INORBIT | LEFT_EARTH))
              and not (st[n] & ERROR)}
    gone1 = {n for n in claims if st[n] & DESTROYED}
    inorb1 = {n for n in claims if (st[n] & INORBIT) and not (st[n] & DESTROYED)
              and not (st[n] & LEFT_EARTH)}
    v1 = (gone1 - ctdec) | (inorb1 & ctdec)
    excluded_transition = both - claims - {n for n in both if st[n] & ERROR}

    # v2, full history.
    hist, _ = H.build_histories()
    kind = {}
    for n in both:
        ks = {H.disposition(r["JCAT"], hist)[0] for r in sat[n]}
        kind[n] = ks.pop() if len(ks) == 1 else "ambiguous"
    gone2 = {n for n in both if kind[n] == "gone"}
    inorb2 = {n for n in both if kind[n] == "inorbit"}
    v2 = (gone2 - ctdec) | (inorb2 & ctdec)

    def cat(n):
        s = st[n]
        if s & ERROR:
            return "ERR (error entry)"
        if s & {"E", "C"}:
            return "E or C (explosion, collision)"
        if s & {"DK", "ATT"}:
            return "DK or ATT (docking, attachment)"
        if s & TRANSITION:
            return "other transition (TFR, GRP, N, ...)"
        if s & {"OX"}:
            return "OX (in orbit, tracking lost)"
        if s & INORBIT:
            return "O or AO (in orbit)"
        if s & DESTROYED:
            return "gone (R, D, L, AR, ...)"
        return "other: " + "+".join(sorted(s))

    def by_cat(ns):
        return dict(collections.Counter(cat(n) for n in ns).most_common())

    dropped01 = v0 - v1
    added01 = v1 - v0
    res = {
        "unit": "objects present in both CelesTrak SATCAT and GCAT satcat, by NORAD number",
        "shared_objects": len(both),
        "v0_total": len(v0),
        "v0_gcat_gone_celestrak_silent": len(v0_gone_ct_silent),
        "v0_celestrak_decayed_gcat_not_gone": len(v0_ct_decayed_not_gone),
        "v0_celestrak_decayed_gcat_not_gone_by_status": by_cat(v0_ct_decayed_not_gone),
        "v0_by_status": by_cat(v0),
        "v1_total": len(v1),
        "v1_excluded_transition_objects": len(excluded_transition),
        "v1_excluded_transition_that_were_v0_disagreements":
            len(excluded_transition & v0),
        "v0_to_v1_dropped": len(dropped01),
        "v0_to_v1_dropped_by_status": by_cat(dropped01),
        "v0_to_v1_added": len(added01),
        "v0_to_v1_added_by_status": by_cat(added01),
        "v2_total": len(v2),
        "v1_to_v2_dropped": len(v1 - v2),
        "v1_to_v2_dropped_by_status": by_cat(v1 - v2),
        "v1_to_v2_added": len(v2 - v1),
        "v1_to_v2_added_by_status": by_cat(v2 - v1),
        "v0_and_v2": len(v0 & v2),
    }
    assert len(v0) == 932 and len(v1) == 261, (len(v0), len(v1))
    assert len(v0) - len(dropped01) + len(added01) == len(v1)
    assert len(v1) - len(v1 - v2) + len(v2 - v1) == len(v2)
    (HERE / "count_ledger.json").write_text(json.dumps(res, indent=2))
    for k, v in res.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
