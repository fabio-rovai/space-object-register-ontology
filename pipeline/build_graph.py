"""Emit the reified assertion graph as Turtle text.

Turtle is written directly as text rather than through an rdflib Graph, because
at this scale the parse-then-serialise round trip is the slow path. The result
is parse-verified afterwards.
"""
import csv, re, json, collections, pathlib, datetime, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from reconcile import (load_celestrak, load_gcat, DESTROYED, TRANSITION,
                       INORBIT, LEFT_EARTH, ERROR, LOST, norm_status)

ROOT = pathlib.Path(__file__).resolve().parent.parent
HARVEST = "2026-08-18"
NS = "https://gov.tesseract.academy/def/space#"
COSPAR = re.compile(r"^\d{4}-\d{3}[A-Z]{1,3}$")
NORADP = re.compile(r"^[0-9]{1,6}$")

def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

def main():
    ct = load_celestrak()
    sat, _, sat_nona = load_gcat("gcat_satcat.tsv")
    aux, _, _ = load_gcat("gcat_auxcat.tsv")
    fto, _, _ = load_gcat("gcat_ftocat.tsv")
    k100, _, _ = load_gcat("gcat_satcat100k.tsv")
    allg = set(sat) | set(aux) | set(fto) | set(k100)

    cos_card = collections.Counter(ct[n]["OBJECT_ID"].strip() for n in ct)
    out = []
    w = out.append
    w("@prefix space: <https://gov.tesseract.academy/def/space#> .")
    w("@prefix scheme: <https://gov.tesseract.academy/def/space/scheme#> .")
    w("@prefix obj: <https://gov.tesseract.academy/id/space/object/> .")
    w("@prefix a1: <https://gov.tesseract.academy/id/space/assertion/> .")
    w("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .")
    w("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .")
    w("")
    D = f'"{HARVEST}"^^xsd:date'
    counts = collections.Counter()

    for n, r in ct.items():
        o = f"obj:{n}"
        e = f"{o}-ct"
        w(f"{e} a space:CatalogueEntry ; space:aboutObject {o} ; rdfs:label \"{esc(r['OBJECT_NAME'])}\" .")
        counts["entries"] += 1
        # identifier assertions
        for scm, val, pat in (("norad", n, NORADP), ("cospar", r["OBJECT_ID"].strip(), COSPAR)):
            conf = "true" if pat.match(val) else "false"
            card = cos_card[val] if scm == "cospar" else 1
            aid = f"a1:ct-{scm}-{n}-{HARVEST}"
            w(f"{aid} a space:IdentifierAssertion ; space:assertedBy space:CelestrakSatcat ; "
              f"space:assertedOn {D} ; space:aboutEntry {e} ; space:inScheme scheme:{scm} ; "
              f'space:identifierValue "{esc(val)}" ; space:schemeConformant {conf} ; '
              f"space:resolutionCardinality {card} .")
            counts["ident"] += 1
            if conf == "false":
                w(f"{e} a space:Defect , space:IdentifierCollision .")
            if card > 1:
                w(f"{e} space:exhibitsDefect {e}-collision . {e}-collision a space:IdentifierCollision .")
                counts["collision"] += 1
        # disposition: silence is a position
        dec = r["DECAY_DATE"].strip()
        disp = "scheme:Reentered" if dec else "scheme:OnOrbit"
        aid = f"a1:ct-disp-{n}-{HARVEST}"
        w(f"{aid} a space:DispositionAssertion ; space:assertedBy space:CelestrakSatcat ; "
          f"space:assertedOn {D} ; space:aboutEntry {e} ; space:disposition {disp}"
          + (f' ; space:dispositionDate "{esc(dec)}"' if dec else "") + " .")
        counts["disp"] += 1

    for n, phases in sat.items():
        o = f"obj:{n}"
        e = f"{o}-gc"
        sts = {norm_status(p.get("Status", "")) for p in phases}
        nm = phases[0].get("Name", "")
        w(f"{e} a space:CatalogueEntry ; space:aboutObject {o} ; rdfs:label \"{esc(nm)}\" .")
        counts["entries"] += 1
        if sts & ERROR:
            note = next((p.get("Name", "") for p in phases), "")
            w(f"a1:gc-exist-{n}-{HARVEST} a space:ExistenceAssertion ; space:assertedBy space:GcatSatcat ; "
              f"space:assertedOn {D} ; space:aboutEntry {e} ; space:correspondsToRealObject false ; "
              f'space:existenceNote "{esc(note)}" .')
            counts["exist"] += 1
            if n in ct:
                w(f"{o} space:exhibitsDefect {o}-phantom . {o}-phantom a space:PhantomEntry .")
                counts["phantom"] += 1
                if not ct[n]["DECAY_DATE"].strip():
                    w(f"{o}-phantom a space:PhantomEntryOnOrbit .")
                    counts["phantom_onorbit"] += 1
        if sts & LOST:
            w(f"a1:gc-track-{n}-{HARVEST} a space:TrackingAssertion ; space:assertedBy space:GcatSatcat ; "
              f"space:assertedOn {D} ; space:aboutEntry {e} ; space:currentlyTracked false .")
            counts["track"] += 1
            if (n in ct and not ct[n]["DECAY_DATE"].strip()
                    and not ct[n]["DATA_STATUS_CODE"].strip()):
                w(f"{o} space:exhibitsDefect {o}-lost . {o}-lost a space:UndisclosedTrackingLoss .")
                counts["undisclosed_loss"] += 1
        gone = bool(sts & DESTROYED)
        left = bool(sts & LEFT_EARTH) and not gone
        inorb = bool(sts & INORBIT) and not gone and not left
        claims = bool(sts & (DESTROYED | INORBIT | LEFT_EARTH)) and not (sts & ERROR)
        disp = ("scheme:Reentered" if gone else "scheme:LeftEarthOrbit" if left
                else "scheme:OnOrbit" if inorb else "scheme:PhaseTransition")
        dd = phases[-1].get("DDate", "").strip()
        w(f"a1:gc-disp-{n}-{HARVEST} a space:DispositionAssertion ; space:assertedBy space:GcatSatcat ; "
          f"space:assertedOn {D} ; space:aboutEntry {e} ; space:disposition {disp}"
          + (f' ; space:dispositionDate "{esc(dd)}"' if dd and dd != "-" else "") + " .")
        counts["disp"] += 1
        # cross-source disposition disagreement
        if n in ct and claims:
            ctgone = bool(ct[n]["DECAY_DATE"].strip())
            disagree = (gone and not ctgone) or (inorb and ctgone)
            if disagree:
                w(f"{o} space:exhibitsDefect {o}-dispdis . {o}-dispdis a space:DispositionDisagreement ; "
                  f'space:disagreementField "disposition" ; '
                  f"space:disagreementBetween space:CelestrakSatcat , space:GcatSatcat .")
                counts["disp_disagree"] += 1
        # duplicate NORAD inside GCAT
        if len({p.get("JCAT", "")[:6] for p in phases}) > 1:
            w(f"{o} space:exhibitsDefect {o}-dup . {o}-dup a space:IdentifierCollision ; "
              f"space:disagreementBetween space:GcatSatcat .")
            counts["gcat_dup"] += 1

    # attribution and characterisation gaps inside CelesTrak itself
    for n, r in ct.items():
        if r["DECAY_DATE"].strip():
            continue
        if r["OWNER"].strip() == "TBD":
            w(f"obj:{n} space:exhibitsDefect obj:{n}-unattr . obj:{n}-unattr a space:UnattributedObject .")
            counts["unattributed"] += 1
        if not r["RCS"].strip():
            w(f"obj:{n} space:exhibitsDefect obj:{n}-unchar . obj:{n}-unchar a space:UncharacterisedObject .")
            counts["uncharacterised"] += 1

    # coverage gaps, checked against every GCAT catalogue
    for n in set(ct) - allg:
        w(f"obj:{n} space:exhibitsDefect obj:{n}-gap . obj:{n}-gap a space:CoverageGap .")
        counts["coverage_gap"] += 1
    # objects GCAT tracks with no NORAD number
    for i, r in enumerate(sat_nona):
        w(f"obj:nna-{i} a space:SpaceObject ; rdfs:label \"{esc(r.get('Name',''))}\" ; "
          f"space:exhibitsDefect obj:nna-{i}-un . obj:nna-{i}-un a space:UnnumberedObject .")
        counts["unnumbered"] += 1

    p = ROOT / "reports" / "graph.ttl"
    p.write_text("\n".join(out) + "\n")
    print("wrote", p, f"{p.stat().st_size/1e6:.1f} MB")
    print(json.dumps(counts, indent=1))

if __name__ == "__main__":
    main()

def emit_defect_subgraph():
    """Write the defect layer on its own, for verification at sane runtime."""
    root = pathlib.Path(__file__).resolve().parent.parent
    src = (root / "reports" / "graph.ttl").read_text().splitlines()
    keep = ("PhantomEntry", "UndisclosedTrackingLoss", "DispositionDisagreement",
            "CoverageGap", "UnnumberedObject", "IdentifierCollision",
            "UnattributedObject", "UncharacterisedObject")
    out = src[:6] + [l for l in src if any(k in l for k in keep)]
    (root / "reports" / "defects.ttl").write_text("\n".join(out) + "\n")
