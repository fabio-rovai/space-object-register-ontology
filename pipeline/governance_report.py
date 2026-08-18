"""Dual-computation governance gate.

Every headline number is computed twice: set-based in Python from the source
files, and via SPARQL over the emitted graph. Any disagreement exits non-zero.
"""
import json, sys, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rdflib
from reconcile import (load_celestrak, load_gcat, DESTROYED, INORBIT,
                       LEFT_EARTH, ERROR, LOST, norm_status)

ROOT = pathlib.Path(__file__).resolve().parent.parent
NS = "https://gov.tesseract.academy/def/space#"

def python_side():
    ct = load_celestrak()
    sat, _, nona = load_gcat("gcat_satcat.tsv")
    aux, _, _ = load_gcat("gcat_auxcat.tsv")
    fto, _, _ = load_gcat("gcat_ftocat.tsv")
    k100, _, _ = load_gcat("gcat_satcat100k.tsv")
    allg = set(sat) | set(aux) | set(fto) | set(k100)
    st = {n: {norm_status(p.get("Status", "")) for p in v} for n, v in sat.items()}
    ctdec = {n for n in ct if ct[n]["DECAY_DATE"].strip()}
    onorb = {n for n in ct if not ct[n]["DECAY_DATE"].strip()}
    phantom = {n for n in sat if (st[n] & ERROR) and n in ct}
    claims = {n for n in sat if n in ct
              and (st[n] & (DESTROYED | INORBIT | LEFT_EARTH)) and not (st[n] & ERROR)}
    gone = {n for n in claims if st[n] & DESTROYED}
    inorb = {n for n in claims if (st[n] & INORBIT)
             and not (st[n] & DESTROYED) and not (st[n] & LEFT_EARTH)}
    return {
        "PhantomEntry": len(phantom),
        "PhantomEntryOnOrbit": len({n for n in phantom if n not in ctdec}),
        "UndisclosedTrackingLoss": len({n for n in sat if (st[n] & LOST) and n in ct
                                        and n not in ctdec
                                        and not ct[n]["DATA_STATUS_CODE"].strip()}),
        "DispositionDisagreement": len((gone - ctdec) | (inorb & ctdec)),
        "CoverageGap": len(set(ct) - allg),
        "UnnumberedObject": len(nona),
        "UnattributedObject": len({n for n in onorb if ct[n]["OWNER"].strip() == "TBD"}),
        "UncharacterisedObject": len({n for n in onorb if not ct[n]["RCS"].strip()}),
        "IdentifierCollision": len({n for n in sat
                                    if len({p.get("JCAT","")[:6] for p in sat[n]}) > 1}),
    }

def sparql_side():
    g = rdflib.Graph()
    # Full graph by default. rdflib takes over an hour and about 5 GB on it, so
    # set SORO_FAST=1 to verify against the defect subgraph instead when iterating.
    # The published numbers come from the full graph.
    import os
    name = "defects.ttl" if os.environ.get("SORO_FAST") else "graph.ttl"
    g.parse(ROOT / "reports" / name, format="turtle")
    print(f"  graph parsed: {len(g):,} triples", flush=True)
    out = {}
    for cls in ["PhantomEntry", "PhantomEntryOnOrbit", "UndisclosedTrackingLoss",
                "DispositionDisagreement", "CoverageGap", "UnnumberedObject",
                "UnattributedObject", "UncharacterisedObject"]:
        q = f"SELECT (COUNT(DISTINCT ?n) AS ?c) WHERE {{ ?n a <{NS}{cls}> }}"
        out[cls] = int(list(g.query(q))[0][0])
    q = (f"SELECT (COUNT(DISTINCT ?n) AS ?c) WHERE {{ ?n a <{NS}IdentifierCollision> ; "
         f"<{NS}disagreementBetween> <{NS}GcatSatcat> }}")
    out["IdentifierCollision"] = int(list(g.query(q))[0][0])
    return out, len(g)

def main():
    print("computing Python side...", flush=True)
    p = python_side()
    print("computing SPARQL side...", flush=True)
    s, ntriples = sparql_side()
    ok = True
    print(f"\n{'defect class':32} {'python':>10} {'sparql':>10}  agree")
    for k in sorted(p):
        a = p[k] == s.get(k)
        ok &= a
        print(f"{k:32} {p[k]:>10,} {s.get(k,'-'):>10,}  {'YES' if a else 'NO  <-- MISMATCH'}")
    (ROOT / "reports" / "governance.json").write_text(json.dumps(
        {"python": p, "sparql": s, "triples": ntriples, "agree": ok}, indent=2))
    print(f"\ngraph triples: {ntriples:,}")
    print("ALL CROSS-CHECKS AGREE" if ok else "CROSS-CHECK FAILURE")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
