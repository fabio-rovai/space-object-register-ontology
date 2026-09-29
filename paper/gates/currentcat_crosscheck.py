"""Cross-check history_check.py against GCAT's own derived Current Catalog.

history_check.py reconstructs each object's latest phase from the first-phase record
and the event catalog, and resolves docked objects through their hosts. That is our
code reading GCAT. The Current Catalog (currentcat) is GCAT's own derivation of the
same thing, "Most recent phase for each S and A object", written by the catalogue's
maintainer. Agreeing with it is evidence the reconstruction follows the source rather
than our assumptions about the source.

currentcat carries a free-text ExpandedStatus rather than a code. Every template that
occurs is mapped below; an unmapped template raises instead of being guessed.
currentcat postdates the frozen files (data update 28 Sep 2026), so objects whose
latest phase ends after 18 Aug 2026 are reported as time skew and not compared.

Run: python3 paper/gates/currentcat_crosscheck.py
Writes: paper/gates/currentcat_results.json
"""
import collections
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "pipeline"))
import history_check as H  # noqa: E402
from reconcile import load_celestrak, load_gcat  # noqa: E402

CURRENT = ROOT / "data" / "gcat_currentcat_20260928.tsv"

TEMPLATES = [
    # (regex on ExpandedStatus, kind)
    (r"^(Reentered|Deorbited into|Landed on Earth|Landed attached to|Landed inside|"
     r"Possibly landed inside|Reentered attached to|Reentered inside|Targeted suborbital|"
     r"Crashed on Earth)", "gone"),
    (r"^(In Earth orbit|Lost$|Attached to|Docked with)", "inorbit"),
    (r"^(Exploded|Reflown as catalog|Launched from)", "unrecorded"),
    (r"^(Impact attached to)", "impact_attached"),
    (r"^(In |Impacted |On |Landed on |Operating on )", "left"),
]


def kind_of(expanded):
    for rx, k in TEMPLATES:
        if re.search(rx, expanded):
            return k
    raise ValueError(f"unmapped currentcat status: {expanded!r}")


def main():
    ct = load_celestrak()
    sat, _, _ = load_gcat("gcat_satcat.tsv")
    hist, _ = H.build_histories()
    cur = {r["JCAT"]: r for r in H.load_tsv(CURRENT)}
    both = sorted(set(ct) & set(sat), key=int)
    ctdec = {n for n in both if ct[n]["DECAY_DATE"].strip()}

    ours, theirs, skew, missing = {}, {}, set(), set()
    for n in both:
        if len(sat[n]) != 1:          # the three identifier collisions
            continue
        j = sat[n][0]["JCAT"]
        ours[n] = H.disposition(j, hist)[0]
        r = cur.get(j)
        if r is None:
            missing.add(n)
            continue
        dd = H.vague_date(r.get("DDate", ""))
        if dd is not None and dd > H.FREEZE:
            skew.add(n)
            continue
        k = kind_of(r["ExpandedStatus"])
        if k == "impact_attached":    # host impacted: Earth reentry if CelesTrak decayed
            k = "gone"
        theirs[n] = k

    compared = sorted(set(ours) & set(theirs), key=int)
    mism = [n for n in compared if ours[n] != theirs[n]
            and not (ours[n] in ("error",) and theirs[n] in ("gone", "inorbit"))]

    def count(kinds):
        g = {n for n, k in kinds.items() if k == "gone"}
        o = {n for n, k in kinds.items() if k == "inorbit"}
        return (g - ctdec) | (o & ctdec)

    d_ours = count({n: ours[n] for n in compared if ours[n] != "error"})
    d_theirs = count({n: theirs[n] for n in compared if ours[n] != "error"})
    res = {
        "compared_objects": len(compared),
        "time_skew_excluded": len(skew),
        "missing_from_currentcat": len(missing),
        "kind_mismatches": len(mism),
        "mismatch_pairs": dict(collections.Counter(f"{ours[n]}->{theirs[n]}" for n in mism)),
        "mismatch_examples": {n: {"name": ct[n]["OBJECT_NAME"], "ours": ours[n],
                                  "currentcat": cur[sat[n][0]["JCAT"]]["ExpandedStatus"],
                                  "ct_decay": ct[n]["DECAY_DATE"]} for n in mism[:30]},
        "disagreement_count_history_check": len(d_ours),
        "disagreement_count_currentcat": len(d_theirs),
        "in_history_only": sorted(d_ours - d_theirs, key=int),
        "in_currentcat_only": sorted(d_theirs - d_ours, key=int),
    }
    (HERE / "currentcat_results.json").write_text(json.dumps(res, indent=2))
    for k, v in res.items():
        if k != "mismatch_examples":
            print(f"{k}: {v}")
    print("examples:", json.dumps(res["mismatch_examples"], indent=1)[:3000])


if __name__ == "__main__":
    main()
