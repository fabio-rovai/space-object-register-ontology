def python_side():
    ct = load_celestrak()
    sat, _, nona = load_gcat("gcat_satcat.tsv")
    aux, _, _ = load_gcat("gcat_auxcat.tsv")
    fto, _, _ = load_gcat("gcat_ftocat.tsv")
    allg = set(sat) | set(aux) | set(fto)
    st = {n: {p.get("Status", "").strip() for p in v} for n, v in sat.items()}
    ctdec = {n for n in ct if ct[n]["DECAY_DATE"].strip()}
    phantom = {n for n in sat if (st[n] & ERROR) and n in ct}
    return {
        "PhantomEntry": len(phantom),
        "PhantomEntryOnOrbit": len({n for n in phantom if n not in ctdec}),
        "UndisclosedTrackingLoss": len({n for n in sat if (st[n] & LOST) and n in ct and n not in ctdec}),
        "DispositionDisagreement": len({
            n for n in sat if n in ct
            and (bool(st[n] & GONE) != (n in ctdec))
            and not ((n in ctdec) and (st[n] & LEFT_EARTH) and not (st[n] & GONE))}),
        "CoverageGap": len(set(ct) - allg),
        "UnnumberedObject": len(nona),
        "IdentifierCollision": len({n for n in sat if len({p.get("JCAT","")[:6] for p in sat[n]}) > 1}),
    }
