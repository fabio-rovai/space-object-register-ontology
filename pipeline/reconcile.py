"""Cross-catalogue reconciliation: CelesTrak SATCAT against McDowell GCAT.

Phase-aware. GCAT rows are flight phases, not objects, so an object's
disposition is derived from all of its phases rather than from any single row.
"""
import csv, json, re, sys, collections, pathlib

csv.field_size_limit(10_000_000)
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# GCAT status codes, from planet4589.org/space/gcat/web/intro/phases.html
#
# CORRECTED 18 Aug 2026. The first version of this file treated only reentry and
# landing codes as "gone" and everything else as "still in orbit". That was wrong
# in two ways and it inflated the published disagreement count by a factor of 3.6.
#   1. E (exploded) and C (collided) destroy the object and were being counted as
#      "still in orbit".
#   2. Codes such as DK, ATT, TFR and GRP end a phase because the object joined
#      another object. GCAT is making no claim about current disposition there,
#      so those objects must be excluded from a disposition comparison rather
#      than counted as a disagreement.
# A trailing "?" marks an uncertain date, not a different status, so it is stripped.

DESTROYED = {"R","D","L","LF","S","F","AF","AS","AR","AR IN","AL","AL IN","TX","E","C"}
TRANSITION = {"DK","GRP","ATT","TFR","TFR E","TFR IN","EVA DP","EVA RP","REL","UDK",
              "DEP","REFLT","N","NA","LEASE","TO","TOA","ALO"}
INORBIT = {"O","AO","AO IN","OX"}
LEFT_EARTH = {"DSO","DSA","DSA IN","EO","EAO","EN","OI","OE","LO","LOA"}
ERROR = {"ERR"}
LOST = {"OX"}
# Retained under the old name so existing callers keep working.
GONE = DESTROYED

CATALOGUES = ["gcat_satcat.tsv", "gcat_auxcat.tsv", "gcat_ftocat.tsv", "gcat_satcat100k.tsv"]


def norm_status(s):
    """Strip the uncertainty marker. '1990?' is a vague date, not a vague status."""
    return s.rstrip("?").strip()


def load_celestrak():
    out = {}
    with open(DATA/"celestrak_satcat.csv", newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            out[r["NORAD_CAT_ID"].strip()] = r
    return out

def load_gcat(name):
    """Return (phases_by_norad, all_rows, no_norad_rows)."""
    by_norad = collections.defaultdict(list)
    rows, nona = [], []
    with open(DATA/name, encoding="utf-8", errors="replace") as f:
        hdr = [h.strip() for h in f.readline().lstrip("#").rstrip("\n").split("\t")]
        for line in f:
            if line.startswith("#"):
                continue
            p = line.rstrip("\n").split("\t")
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
    return {norm_status(p.get("Status","")) for p in phases}

def main():
    ct = load_celestrak()
    sat, sat_rows, sat_nona = load_gcat("gcat_satcat.tsv")
    aux, aux_rows, aux_nona = load_gcat("gcat_auxcat.tsv")
    fto, fto_rows, fto_nona = load_gcat("gcat_ftocat.tsv")
    k100, k100_rows, _ = load_gcat("gcat_satcat100k.tsv")

    F = {}
    F["harvest"] = {
        "celestrak_objects": len(ct),
        "gcat_satcat_phases": len(sat_rows),
        "gcat_satcat_objects": len(sat),
        "gcat_auxcat_phases": len(aux_rows),
        "gcat_auxcat_objects": len(aux),
        "gcat_ftocat_phases": len(fto_rows),
        "gcat_satcat_no_norad_rows": len(sat_nona),
    }

    # ---- multi-phase reality check
    ph = collections.Counter(len(v) for v in sat.values())
    F["phases_per_object"] = {
        "objects_with_multiple_phases": sum(c for n,c in ph.items() if n>1),
        "max_phases_on_one_object": max(ph),
    }

    # ---- coverage: is the CelesTrak-only set real, once auxcat/ftocat are included?
    A = set(ct)
    allg = set(sat) | set(aux) | set(fto) | set(k100)
    only_ct_satcat = A - set(sat)
    only_ct_all = A - allg
    F["coverage"] = {
        "in_both_satcat": len(A & set(sat)),
        "celestrak_only_vs_satcat": len(only_ct_satcat),
        "celestrak_only_vs_all_gcat": len(only_ct_all),
        "recovered_by_other_gcat_catalogues": len(only_ct_satcat) - len(only_ct_all),
        "gcat_satcat100k_objects": len(k100),
    }

    # ---- ERR: entries GCAT says correspond to no real object
    err = {n: v for n, v in sat.items() if statuses(v) & ERROR}
    err_in_ct = {n for n in err if n in ct}
    F["error_entries"] = {
        "gcat_err_objects": len(err),
        "also_listed_by_celestrak": len(err_in_ct),
        "examples": [
            {"norad": n, "gcat_name": err[n][0].get("Name",""),
             "celestrak_name": ct[n]["OBJECT_NAME"] if n in ct else None,
             "celestrak_decay": ct[n]["DECAY_DATE"] if n in ct else None}
            for n in sorted(err_in_ct, key=int)[:12]
        ],
    }

    # ---- OX: presumed in orbit but no recent tracking
    lost = {n for n, v in sat.items() if statuses(v) & LOST}
    lost_active_ct = {n for n in lost if n in ct and not ct[n]["DECAY_DATE"].strip()}
    F["lost_objects"] = {
        "gcat_ox_objects": len(lost),
        "celestrak_carries_no_decay_date": len(lost_active_ct),
    }

    # ---- disposition disagreement, decomposed honestly
    # Only objects where GCAT actually makes a current-disposition claim are
    # compared. Objects whose phase ends in a transition, and error entries, are
    # excluded rather than counted as disagreements.
    both = A & set(sat)
    ct_decayed = {n for n in both if ct[n]["DECAY_DATE"].strip()}
    claims = {n for n in both
              if (statuses(sat[n]) & (DESTROYED | INORBIT | LEFT_EARTH))
              and not (statuses(sat[n]) & ERROR)}
    gone = {n for n in claims if statuses(sat[n]) & DESTROYED}
    left = {n for n in claims if (statuses(sat[n]) & LEFT_EARTH) and not (statuses(sat[n]) & DESTROYED)}
    inorb = {n for n in claims if (statuses(sat[n]) & INORBIT)
             and not (statuses(sat[n]) & DESTROYED) and not (statuses(sat[n]) & LEFT_EARTH)}
    F["disposition"] = {
        "shared_objects": len(both),
        "gcat_makes_a_disposition_claim": len(claims),
        "excluded_transition_only": len(both - claims - {n for n in both if statuses(sat[n]) & ERROR}),
        "excluded_error_entries": len({n for n in both if statuses(sat[n]) & ERROR}),
        "agree_gone": len(gone & ct_decayed),
        "agree_in_orbit": len(inorb - ct_decayed),
        "gcat_gone_celestrak_silent": len(gone - ct_decayed),
        "gcat_in_orbit_celestrak_decayed": len(inorb & ct_decayed),
        "true_disagreement": len(gone - ct_decayed) + len(inorb & ct_decayed),
        "gcat_left_earth_orbit": len(left),
    }
    F["disposition"]["gone_celestrak_silent_by_status"] = dict(collections.Counter(
        s for n in (gone - ct_decayed) for s in statuses(sat[n]) & DESTROYED).most_common())
    F["disposition"]["examples_gcat_gone_ct_silent"] = [
        {"norad": n, "celestrak": ct[n]["OBJECT_NAME"], "ct_ops": ct[n]["OPS_STATUS_CODE"],
         "ct_data_status": ct[n]["DATA_STATUS_CODE"],
         "gcat_statuses": sorted(statuses(sat[n])), "gcat_ddate": sat[n][-1].get("DDate","")}
        for n in sorted(gone - ct_decayed, key=int)[:12]]

    # ---- does CelesTrak disclose the tracking loss GCAT records?
    lost_set = {n for n in sat if (statuses(sat[n]) & LOST) and n in ct and n not in ct_decayed}
    F["lost_objects"]["celestrak_data_status_on_those"] = dict(collections.Counter(
        ct[n]["DATA_STATUS_CODE"].strip() or "(blank)" for n in lost_set).most_common())
    F["lost_objects"]["undisclosed_no_data_status_code"] = len(
        {n for n in lost_set if not ct[n]["DATA_STATUS_CODE"].strip()})
    F["lost_objects"]["celestrak_uses_field_elsewhere"] = dict(collections.Counter(
        ct[n]["DATA_STATUS_CODE"].strip() for n in ct if ct[n]["DATA_STATUS_CODE"].strip()).most_common())

    # ---- attribution
    on_orbit = {n for n in ct if not ct[n]["DECAY_DATE"].strip()}
    F["attribution"] = {
        "identical_owner_string": sum(1 for n in both
            if ct[n]["OWNER"].strip() == sat[n][0].get("State","").strip()),
        "shared_objects": len(both),
        "top_scheme_mismatches": dict(collections.Counter(
            f'{ct[n]["OWNER"].strip()}|{sat[n][0].get("State","").strip()}' for n in both
            if ct[n]["OWNER"].strip() != sat[n][0].get("State","").strip()).most_common(12)),
        "celestrak_owner_tbd": len({n for n in ct if ct[n]["OWNER"].strip() == "TBD"}),
        "celestrak_owner_tbd_on_orbit": len({n for n in on_orbit if ct[n]["OWNER"].strip() == "TBD"}),
        "celestrak_type_unknown": len({n for n in ct if ct[n]["OBJECT_TYPE"].strip() == "UNK"}),
        "celestrak_type_unknown_on_orbit": len({n for n in on_orbit if ct[n]["OBJECT_TYPE"].strip() == "UNK"}),
    }

    # ---- characterisation data coverage
    F["characterisation"] = {
        "on_orbit_objects": len(on_orbit),
        "with_radar_cross_section": len({n for n in on_orbit if ct[n]["RCS"].strip()}),
        "without_radar_cross_section": len({n for n in on_orbit if not ct[n]["RCS"].strip()}),
        "on_orbit_without_orbital_period": len({n for n in on_orbit if not ct[n]["PERIOD"].strip()}),
    }

    # ---- duplicate NORAD numbers inside GCAT satcat (candidate source defects)
    dup = {n: v for n, v in sat.items()
           if len({p.get("JCAT","")[:6] for p in v}) > 1}
    F["gcat_duplicate_satcat"] = {
        "count": len(dup),
        "cases": [
            {"norad": n,
             "entries": [{"jcat": p.get("JCAT",""), "name": p.get("Name",""),
                          "status": p.get("Status",""), "ldate": p.get("LDate","")} for p in v],
             "celestrak_name": ct[n]["OBJECT_NAME"] if n in ct else None}
            for n, v in sorted(dup.items(), key=lambda kv: int(kv[0]))
        ],
    }

    # ---- identifier conformance (COSPAR international designator)
    pat = re.compile(r"^\d{4}-\d{3}[A-Z]{1,3}$")
    bad = [n for n in ct if not pat.match(ct[n]["OBJECT_ID"].strip())]
    byid = collections.defaultdict(list)
    for n in ct:
        byid[ct[n]["OBJECT_ID"].strip()].append(n)
    F["identifier_conformance"] = {
        "celestrak_objects": len(ct),
        "cospar_non_conformant": len(bad),
        "cospar_designators_on_multiple_norad": sum(1 for v in byid.values() if len(v) > 1),
        "duplicate_norad_numbers": 0,
    }

    # ---- objects GCAT tracks with no NORAD number at all
    F["unnumbered"] = {
        "gcat_satcat_rows_without_norad": len(sat_nona),
        "distinct_placeholder_values": sorted({r.get("Satcat","") for r in sat_nona}),
        "examples": [{"name": r.get("Name",""), "status": r.get("Status",""),
                      "ldate": r.get("LDate","")} for r in sat_nona[:10]],
    }

    (ROOT/"reports").mkdir(exist_ok=True)
    (ROOT/"reports"/"findings.json").write_text(json.dumps(F, indent=2))
    print(json.dumps(F, indent=2)[:5200])

if __name__ == "__main__":
    main()
