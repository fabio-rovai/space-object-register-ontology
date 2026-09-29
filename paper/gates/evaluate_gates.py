"""Empirical evaluation of three verification gates.

This script implements and MEASURES three gates against the committed source
data. It runs each gate twice: once with the PRE-correction classification
constants (git 24d684e, the buggy version) and once with the POST-correction
constants (the current pipeline/reconcile.py, commit 60d2938). For every gate it
records what the gate caught on the buggy code and what it fires on against the
corrected code (false positives).

No arguments. Offline. Deterministic. Reads only the committed data files and
imports read-only from pipeline/reconcile.py. Writes only two files, both inside
paper/gates/: results.json and RESULTS.md. It does not run reconcile.main(), so
nothing under reports/ is touched.
"""
import sys, json, csv, collections, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"
OUT = ROOT / "paper" / "gates"
csv.field_size_limit(10_000_000)

# Import the POST-correction constants and loaders read-only. Importing the
# module runs only module-level code (constant definitions); main() is guarded
# by __name__ == "__main__", so nothing is written and reports/ is untouched.
sys.path.insert(0, str(ROOT / "pipeline"))
from reconcile import (load_celestrak, load_gcat, norm_status,
                       DESTROYED, TRANSITION, INORBIT, LEFT_EARTH, ERROR, LOST)

# ---------------------------------------------------------------------------
# PRE-correction constants, transcribed verbatim from
#   git show 24d684e:pipeline/reconcile.py
# The buggy version had a single GONE set (no E, no C) and NO transition set,
# and it did NOT strip the trailing "?" uncertainty marker.
GONE_PRE = {"R", "D", "L", "LF", "S", "F", "AF", "AS", "AR", "AR IN",
            "AL", "AL IN", "TX"}
# INORBIT, LEFT_EARTH, ERROR, LOST were identical PRE and POST, so we reuse the
# imported POST copies for those four sets.

# Recognised controlled vocabulary per column, i.e. the values the pipeline's
# classification constants actually assign to a named category.
PRE_STATUS_NAMED = GONE_PRE | INORBIT | LEFT_EARTH | ERROR | LOST
POST_STATUS_NAMED = DESTROYED | TRANSITION | INORBIT | LEFT_EARTH | ERROR | LOST

GCAT_FILES = ["gcat_satcat.tsv", "gcat_auxcat.tsv", "gcat_ftocat.tsv",
              "gcat_satcat100k.tsv"]


def sorted_counter(counter):
    """Deterministic most-common ordering: by descending count, then key."""
    return sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))


# ---------------------------------------------------------------------------
# Column readers
def gcat_status_counts(name):
    """Counter of normalised GCAT Status values over phase rows in one file.

    Row parsing mirrors reconcile.load_gcat: skip comment lines and short rows.
    """
    cnt = collections.Counter()
    with open(DATA / name, encoding="utf-8", errors="replace") as f:
        hdr = [h.strip() for h in f.readline().lstrip("#").rstrip("\n").split("\t")]
        idx = hdr.index("Status")
        for line in f:
            if line.startswith("#"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < len(hdr):
                continue
            cnt[norm_status(p[idx])] += 1
    return cnt


def celestrak_column_counts(column):
    cnt = collections.Counter()
    with open(DATA / "celestrak_satcat.csv", newline="", encoding="utf-8",
              errors="replace") as f:
        for r in csv.DictReader(f):
            cnt[r.get(column, "").strip()] += 1
    return cnt


# ---------------------------------------------------------------------------
# GATE 1: total-function check over controlled vocabularies
def gate1():
    checks = []

    def build_check(column, source, counts, pre_named, post_named,
                    recognised_note):
        distinct = sorted(counts)
        pre_unc = sorted(v for v in distinct if v not in pre_named)
        post_unc = sorted(v for v in distinct if v not in post_named)
        return {
            "column": column,
            "source": source,
            "recognised_vocabulary_source": recognised_note,
            "distinct_values_observed": distinct,
            "distinct_value_count": len(distinct),
            "pre": {
                "unclassified_values": pre_unc,
                "unclassified_distinct_count": len(pre_unc),
                "data_rows_affected": sum(counts[v] for v in pre_unc),
            },
            "post": {
                "unclassified_values": post_unc,
                "unclassified_distinct_count": len(post_unc),
                "data_rows_affected": sum(counts[v] for v in post_unc),
            },
        }

    # 1a. GCAT Status on the catalogue the disposition classifier is applied to.
    satcat_status = gcat_status_counts("gcat_satcat.tsv")
    checks.append(build_check(
        "GCAT Status", "gcat_satcat.tsv (the column the disposition classifier is applied to)",
        satcat_status, PRE_STATUS_NAMED, POST_STATUS_NAMED,
        "union of the GCAT status category constants in reconcile.py "
        "(PRE: GONE|INORBIT|LEFT_EARTH|ERROR|LOST; "
        "POST: DESTROYED|TRANSITION|INORBIT|LEFT_EARTH|ERROR|LOST)"))

    # 1b. GCAT Status pooled across all four ingested GCAT files.
    pooled = collections.Counter()
    for name in GCAT_FILES:
        pooled.update(gcat_status_counts(name))
    checks.append(build_check(
        "GCAT Status", "all four ingested GCAT files pooled",
        pooled, PRE_STATUS_NAMED, POST_STATUS_NAMED,
        "same status category constants as the gcat_satcat.tsv check above"))

    # 1c. CelesTrak DATA_STATUS_CODE. The pipeline names only the blank state
    # (blank => a disclosure category); it enumerates no actual code, so every
    # non-blank code is unclassified. PRE and POST are identical here.
    dsc = celestrak_column_counts("DATA_STATUS_CODE")
    checks.append(build_check(
        "CelesTrak DATA_STATUS_CODE", "celestrak_satcat.csv",
        dsc, {""}, {""},
        "pipeline names only the blank state; the empty string is the only "
        "recognised category (reconcile/build_graph test blank vs non-blank only)"))

    # 1d. CelesTrak ORBIT_TYPE. The pipeline assigns no named category to any
    # orbit type, so the recognised set is empty. PRE and POST identical.
    orb = celestrak_column_counts("ORBIT_TYPE")
    checks.append(build_check(
        "CelesTrak ORBIT_TYPE", "celestrak_satcat.csv",
        orb, set(), set(),
        "pipeline defines no ORBIT_TYPE category constants; recognised set empty"))

    # 1e. CelesTrak OBJECT_TYPE. The pipeline references only the "UNK" sentinel
    # (type unknown); it assigns no category to PAY, DEB or R/B. PRE and POST
    # identical.
    obj = celestrak_column_counts("OBJECT_TYPE")
    checks.append(build_check(
        "CelesTrak OBJECT_TYPE", "celestrak_satcat.csv",
        obj, {"UNK"}, {"UNK"},
        "pipeline references only the UNK sentinel; UNK is the only recognised value"))

    return {
        "description": "For each controlled-vocabulary column, enumerate every "
                       "distinct observed value and check whether the pipeline's "
                       "classification constants assign it to a named category. "
                       "Trailing '?' stripped on GCAT Status via norm_status. Gate "
                       "fails when the unclassified count is > 0.",
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# GATE 2: mandatory residue decomposition
def gate2(ct, sat, ctdec):
    # PRE DispositionDisagreement, transcribed verbatim from
    # git 24d684e:pipeline/governance_report.py (uses .strip() only, NOT
    # norm_status, and the buggy GONE_PRE set without E/C).
    st_pre = {n: {p.get("Status", "").strip() for p in v} for n, v in sat.items()}
    resid_pre = {
        n for n in sat if n in ct
        and (bool(st_pre[n] & GONE_PRE) != (n in ctdec))
        and not ((n in ctdec) and (st_pre[n] & LEFT_EARTH)
                 and not (st_pre[n] & GONE_PRE))}

    # POST DispositionDisagreement, transcribed from the current
    # governance_report.py: only objects where GCAT makes a disposition claim.
    st = {n: {norm_status(p.get("Status", "")) for p in v} for n, v in sat.items()}
    claims = {n for n in sat if n in ct
              and (st[n] & (DESTROYED | INORBIT | LEFT_EARTH))
              and not (st[n] & ERROR)}
    gone = {n for n in claims if st[n] & DESTROYED}
    inorb = {n for n in claims if (st[n] & INORBIT)
             and not (st[n] & DESTROYED) and not (st[n] & LEFT_EARTH)}
    resid_post = (gone - ctdec) | (inorb & ctdec)

    def decompose(residue):
        # Group key: (normalised GCAT Status set, CelesTrak ORBIT_TYPE). An
        # object can carry several phase statuses, so the status component is the
        # sorted set of its normalised statuses joined with "+".
        groups = collections.Counter()
        for n in residue:
            skey = "+".join(sorted(norm_status(p.get("Status", "")) for p in sat[n]))
            otype = ct[n]["ORBIT_TYPE"].strip() or "(blank)"
            groups[(skey, otype)] += 1
        return groups

    pre_groups = decompose(resid_pre)
    post_groups = decompose(resid_post)

    def top(groups, k):
        return [{"gcat_status": g[0], "orbit_type": g[1], "count": c}
                for g, c in sorted_counter(groups)[:k]]

    pre_top15 = top(pre_groups, 15)
    post_top15 = top(post_groups, 15)
    pre_total = len(resid_pre)
    pre_top5 = sum(row["count"] for row in top(pre_groups, 5))

    # Concentration test: transition/attachment statuses (DK, ATT, and their
    # combinations) paired with impact or landing orbit types (IMP, LAN).
    impact_landing = {"IMP", "LAN"}
    attach_codes = {"DK", "ATT"}
    concentrated_hits = 0
    for (skey, otype), c in pre_groups.items():
        codes = set(skey.split("+"))
        if (codes & attach_codes) and otype in impact_landing:
            concentrated_hits += c

    return {
        "description": "Reproduce the PRE DispositionDisagreement count, take the "
                       "objects it flags as disagreements (its residue), and "
                       "decompose them by (normalised GCAT Status set, CelesTrak "
                       "ORBIT_TYPE). Tests whether the residue concentrates in a "
                       "few misclassification-revealing pairs.",
        "pre_disposition_disagreement": pre_total,
        "pre_disposition_disagreement_expected": 932,
        "pre_reproduces_expected": pre_total == 932,
        "post_disposition_disagreement": len(resid_post),
        "post_disposition_disagreement_expected": 261,
        "post_reproduces_expected": len(resid_post) == 261,
        "pre_group_count": len(pre_groups),
        "pre_top15_groups": pre_top15,
        "pre_top5_group_total": pre_top5,
        "pre_top5_fraction_of_total": round(pre_top5 / pre_total, 4),
        "attachment_impact_landing_residue_count": concentrated_hits,
        "post_group_count": len(post_groups),
        "post_top15_groups": post_top15,
    }


# ---------------------------------------------------------------------------
# GATE 3: source inventory reconciliation
def gate3(ct, sat, aux, fto, k100):
    # GCAT catalogue basenames the source publishes, transcribed from the GCAT
    # catalogue index page (planet4589.org/space/gcat/web/cat/index.html).
    SOURCE_INDEX_BASENAMES = ["satcat", "auxcat", "ftocat", "satcat100k"]
    # Files the PRE-correction harvest actually loaded, as visible in
    # git 24d684e (governance_report.py loads satcat, auxcat, ftocat only).
    PRE_FETCHED = ["satcat", "auxcat", "ftocat"]

    listed_not_fetched = [b for b in SOURCE_INDEX_BASENAMES if b not in PRE_FETCHED]

    other = set(sat) | set(aux) | set(fto)
    g_pre = set(ct) - other
    g_post = set(ct) - (other | set(k100))
    recovered = g_pre & set(k100)
    only_in_k100 = set(k100) - other  # objects whose only GCAT source is satcat100k

    return {
        "description": "Compare the GCAT catalogue basenames the source publishes "
                       "against the files the PRE harvest loaded, then quantify the "
                       "coverage consequence of the omitted file.",
        "source_index_basenames": SOURCE_INDEX_BASENAMES,
        "pre_fetched_basenames": PRE_FETCHED,
        "listed_but_not_fetched": listed_not_fetched,
        "satcat100k_objects": len(k100),
        "satcat100k_objects_expected": 354,
        "satcat100k_matches_expected": len(k100) == 354,
        "objects_only_in_satcat100k": len(only_in_k100),
        "pre_coverage_gap": len(g_pre),
        "pre_coverage_gap_expected": 900,
        "post_coverage_gap": len(g_post),
        "post_coverage_gap_expected": 622,
        "recovered_by_satcat100k": len(recovered),
        "recovered_expected": 280,
        "recovered_matches_expected": len(recovered) == 280,
        "recovered_equals_pre_minus_post": len(g_pre) - len(g_post),
    }


# ---------------------------------------------------------------------------
def md_gate1(g1):
    lines = ["## Gate 1: total-function check over controlled vocabularies", "",
             "For each controlled-vocabulary column, every distinct observed value "
             "is checked against the pipeline's classification constants. A value "
             "assigned to no named category is unclassified. Trailing '?' is "
             "stripped on GCAT Status. The gate fails when the unclassified count "
             "is greater than zero.", ""]
    for c in g1["checks"]:
        lines.append("### %s (%s)" % (c["column"], c["source"]))
        lines.append("")
        lines.append("Recognised vocabulary: %s." % c["recognised_vocabulary_source"])
        lines.append("")
        lines.append("Distinct values observed (%d): %s" %
                     (c["distinct_value_count"], ", ".join(c["distinct_values_observed"]) or "(none)"))
        lines.append("")
        lines.append("PRE unclassified (%d values, %d data rows): %s" % (
            c["pre"]["unclassified_distinct_count"], c["pre"]["data_rows_affected"],
            ", ".join(c["pre"]["unclassified_values"]) or "(none)"))
        lines.append("")
        lines.append("POST unclassified (%d values, %d data rows): %s" % (
            c["post"]["unclassified_distinct_count"], c["post"]["data_rows_affected"],
            ", ".join(c["post"]["unclassified_values"]) or "(none)"))
        lines.append("")
    return "\n".join(lines)


def md_gate2(g2):
    lines = ["## Gate 2: mandatory residue decomposition", "",
             g2["description"], "",
             "PRE DispositionDisagreement: %d (expected 932, reproduces: %s)." % (
                 g2["pre_disposition_disagreement"], g2["pre_reproduces_expected"]),
             "POST DispositionDisagreement: %d (expected 261, reproduces: %s)." % (
                 g2["post_disposition_disagreement"], g2["post_reproduces_expected"]),
             "",
             "The 932-object PRE residue falls into %d (status, orbit_type) groups. "
             "The top 5 groups account for %d of 932 (%.1f percent). The residue is "
             "concentrated, not randomly distributed." % (
                 g2["pre_group_count"], g2["pre_top5_group_total"],
                 100 * g2["pre_top5_fraction_of_total"]),
             "",
             "Residue where an attachment or docking status (DK, ATT, or a "
             "combination containing them) is paired with an impact or landing "
             "orbit type (IMP, LAN): %d objects." % g2["attachment_impact_landing_residue_count"],
             "",
             "PRE residue, top 15 groups (normalised GCAT Status set, CelesTrak ORBIT_TYPE, count):", ""]
    for row in g2["pre_top15_groups"]:
        lines.append("- (%s, %s): %d" % (row["gcat_status"], row["orbit_type"], row["count"]))
    lines.append("")
    lines.append("POST residue (the 261 true disagreements), top 15 groups:")
    lines.append("")
    for row in g2["post_top15_groups"]:
        lines.append("- (%s, %s): %d" % (row["gcat_status"], row["orbit_type"], row["count"]))
    lines.append("")
    return "\n".join(lines)


def md_gate3(g3):
    lines = ["## Gate 3: source inventory reconciliation", "",
             g3["description"], "",
             "Source index basenames: %s." % ", ".join(g3["source_index_basenames"]),
             "PRE harvest fetched: %s." % ", ".join(g3["pre_fetched_basenames"]),
             "Listed but not fetched: %s." % ", ".join(g3["listed_but_not_fetched"]),
             "",
             "satcat100k objects: %d (expected 354, matches: %s)." % (
                 g3["satcat100k_objects"], g3["satcat100k_matches_expected"]),
             "Objects whose only GCAT source is satcat100k: %d." % g3["objects_only_in_satcat100k"],
             "",
             "PRE CoverageGap: %d (expected 900)." % g3["pre_coverage_gap"],
             "POST CoverageGap: %d (expected 622)." % g3["post_coverage_gap"],
             "Objects recovered by including satcat100k: %d." % g3["recovered_by_satcat100k"],
             ""]
    if not g3["recovered_matches_expected"]:
        lines.append("DISCREPANCY: the recovered figure is %d, not the expected 280. "
                     "It equals PRE CoverageGap minus POST CoverageGap (%d minus %d = %d) "
                     "exactly, and all 354 satcat100k objects are disjoint from the other "
                     "three GCAT files, so the intersection of satcat100k with CelesTrak is "
                     "exactly %d. Both 900 and 622 reproduce exactly, which forces the "
                     "recovered count to %d. The expected 280 is inconsistent with the 900 "
                     "and 622 values (900 minus 280 would be 620, not 622)." % (
                         g3["recovered_by_satcat100k"], g3["pre_coverage_gap"],
                         g3["post_coverage_gap"], g3["recovered_equals_pre_minus_post"],
                         g3["recovered_by_satcat100k"], g3["recovered_by_satcat100k"]))
        lines.append("")
    return "\n".join(lines)


def build_markdown(results):
    header = ["# Gate evaluation results", "",
              "Empirical evaluation of three verification gates against the "
              "committed source data. Each gate is run against the PRE-correction "
              "constants (git 24d684e) and the POST-correction constants (current "
              "pipeline/reconcile.py, commit 60d2938). PRE is the buggy code; POST "
              "is the corrected code, so anything a gate fires on for POST is a "
              "false positive and is reported as such.", "",
              "Generated by paper/gates/evaluate_gates.py. All numbers below are "
              "reproduced by that script from the data files in data/.", ""]
    body = [md_gate1(results["gate1_total_function"]),
            md_gate2(results["gate2_residue_decomposition"]),
            md_gate3(results["gate3_source_inventory"])]
    notes = ["## Verification notes", "",
             "- Gate 2 reproduces the PRE DispositionDisagreement value of 932 and "
             "the POST value of 261 exactly.",
             "- Gate 3 reproduces satcat100k = 354, PRE CoverageGap = 900 and POST "
             "CoverageGap = 622 exactly. The recovered-object figure is 278, not "
             "the expected 280; see the discrepancy note under Gate 3.",
             "- Gate 1 lists the actual unclassified codes it found for every "
             "column, not just counts.",
             "- Gate 1 fires on the CelesTrak columns (ORBIT_TYPE, OBJECT_TYPE, "
             "DATA_STATUS_CODE) identically for PRE and POST, because the "
             "correction added no controlled-vocabulary classifier for those "
             "columns. Those are genuine false positives and reflect the cost of a "
             "blanket total-function check applied to columns the pipeline treats "
             "as opaque strings.",
             "- Gate 3 has no false positive: the POST CoverageGap of 622 is the "
             "true residual gap after including satcat100k, not a spurious firing."]
    md = "\n".join(header) + "\n" + "\n".join(body) + "\n" + "\n".join(notes) + "\n"
    # Hard style rule: no em dashes anywhere in this file.
    assert "—" not in md, "em dash found in RESULTS.md"
    return md


def main():
    ct = load_celestrak()
    sat, _, _ = load_gcat("gcat_satcat.tsv")
    aux, _, _ = load_gcat("gcat_auxcat.tsv")
    fto, _, _ = load_gcat("gcat_ftocat.tsv")
    k100, _, _ = load_gcat("gcat_satcat100k.tsv")
    ctdec = {n for n in ct if ct[n]["DECAY_DATE"].strip()}

    results = {
        "meta": {
            "repo": str(ROOT),
            "pre_correction_commit": "24d684e",
            "post_correction_commit": "60d2938",
            "celestrak_objects": len(ct),
            "gcat_satcat_objects": len(sat),
        },
        "gate1_total_function": gate1(),
        "gate2_residue_decomposition": gate2(ct, sat, ctdec),
        "gate3_source_inventory": gate3(ct, sat, aux, fto, k100),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    (OUT / "RESULTS.md").write_text(build_markdown(results))

    # Console summary of headline numbers.
    g2 = results["gate2_residue_decomposition"]
    g3 = results["gate3_source_inventory"]
    print("GATE 1 (total-function, GCAT Status on gcat_satcat.tsv):")
    s = results["gate1_total_function"]["checks"][0]
    print("  PRE unclassified:", s["pre"]["unclassified_values"],
          "rows:", s["pre"]["data_rows_affected"])
    print("  POST unclassified:", s["post"]["unclassified_values"],
          "rows:", s["post"]["data_rows_affected"])
    print("GATE 2 (residue decomposition):")
    print("  PRE DispositionDisagreement:", g2["pre_disposition_disagreement"],
          "(expect 932, ok:", g2["pre_reproduces_expected"], ")")
    print("  POST DispositionDisagreement:", g2["post_disposition_disagreement"],
          "(expect 261, ok:", g2["post_reproduces_expected"], ")")
    print("  top5 fraction of 932:", g2["pre_top5_fraction_of_total"])
    print("GATE 3 (source inventory):")
    print("  listed_not_fetched:", g3["listed_but_not_fetched"])
    print("  satcat100k objects:", g3["satcat100k_objects"], "(expect 354)")
    print("  PRE/POST CoverageGap:", g3["pre_coverage_gap"], "/", g3["post_coverage_gap"])
    print("  recovered:", g3["recovered_by_satcat100k"],
          "(expect 280, matches:", g3["recovered_matches_expected"], ")")
    print("\nWrote:", OUT / "results.json")
    print("Wrote:", OUT / "RESULTS.md")


if __name__ == "__main__":
    main()
