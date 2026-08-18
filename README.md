# Space Object Register Ontology

An open ontology for the integrity of space object catalogues, tested against
CelesTrak's SATCAT and Jonathan McDowell's General Catalog of Artificial Space
Objects.

The premise is that identity and disposition are not properties of a space
object. They are dated claims made by a named catalogue. Modelling them that way
makes it possible to say that two catalogues disagree about the same object
without treating either as a data error, which is the situation that actually
holds across every pair of catalogues we have examined.

## What it found

On 18 August 2026, comparing 70,292 CelesTrak objects against 69,391 numbered
GCAT objects:

- **22 entries that GCAT states are not real objects** are still carried by
  CelesTrak. GCAT's own reasons include "Radar error", "Cataloging error" and
  "Delta 150 duplicate".
- **One of those is carried as an on-orbit object.** NORAD 11006 has no decay
  date in CelesTrak, so an entry that GCAT says corresponds to no physical object
  counts as a tracked object still in orbit.
- **1,104 objects GCAT records as no longer tracked** are presented by CelesTrak
  as ordinary on-orbit objects, with nothing marking the loss of tracking.
- **932 objects** on which the two catalogues disagree about whether the object
  is still in orbit, after separating reentry from departure from Earth orbit.
- **900 objects** in CelesTrak that appear in none of the three GCAT catalogues.
- **605 objects GCAT tracks that have no NORAD number at all.**
- **Three NORAD numbers asserted for two different objects inside GCAT**, which
  are candidate defects in GCAT and are reported as such.

And one finding in the other direction, which matters just as much:

- **All 70,292 CelesTrak COSPAR designators are well formed**, with no
  duplicates and no collisions. We expected to find malformation and there is
  none.

Full method, decomposition and caveats are in [BUILD_REPORT.md](BUILD_REPORT.md).

## Why the phantom entries are the interesting part

A catalogue can be perfectly self-consistent and still be wrong about whether a
thing exists. Neither the NORAD number nor the COSPAR designator has any way to
express "this entry corresponds to nothing", so an erroneous entry, once created,
is indistinguishable from a real object by any check performed inside a single
catalogue.

GCAT is the only one of the two registers with a status code for it. That is the
whole argument for cross-catalogue assurance in one sentence.

## Structure

    ontology/space-core.ttl                  OWL 2 core, reified assertions
    ontology/space-schemes.ttl               SKOS registry of identifier schemes
    ontology/shapes-layer1-structural.ttl    structural shapes
    ontology/shapes-layer2-conformance.ttl   scheme conformance shapes
    ontology/shapes-layer3-crosssource.ttl   one shape per defect class
    pipeline/reconcile.py                    cross-catalogue reconciliation
    pipeline/build_graph.py                  emits the assertion graph
    pipeline/governance_report.py            dual computation, non-zero on disagreement

Each identifier scheme declares its own conformance rule as data, so the
pipeline validates against the declared pattern rather than against hard-coded
logic:

```turtle
scheme:cospar a space:IdentifierScheme ;
  space:conformancePattern "^[0-9]{4}-[0-9]{3}[A-Z]{1,3}$" .

scheme:norad a space:IdentifierScheme ;
  space:conformancePattern "^[0-9]{1,6}$" ;
  rdfs:comment "Carries no check digit, so a transcription error produces
                another syntactically valid NORAD number." .
```

## Reproducing it

```bash
python3 pipeline/reconcile.py          # writes reports/findings.json
python3 pipeline/build_graph.py        # writes reports/graph.ttl
python3 pipeline/governance_report.py  # exits non-zero if the two paths disagree
```

The graph is regenerable and is not committed. The CelesTrak file is not
committed either, because the site states no licence. GCAT is CC BY 4.0 and is
cited as the licence requires.

## Data sources

- CelesTrak SATCAT, https://celestrak.org/pub/satcat.csv
- McDowell, Jonathan C., 2020. General Catalog of Artificial Space Objects,
  https://planet4589.org/space/gcat, CC BY 4.0

ESA DISCOS and Space-Track both require a free account and are the next two
sources to add.

## Prior art

Jonathan McDowell's GCAT is the substantive prior art here and deserves saying
so plainly. GCAT already records catalogue errors, tracking loss and phase
structure that no other public catalogue expresses, and several of the findings
above exist only because he recorded them. This work does not replace that. It
makes the disagreements between catalogues machine-checkable, and it reports
three candidate defects back to GCAT rather than publishing them as someone
else's problem.

## Licence

Code MIT. Ontology and documentation CC BY 4.0.

## Contact

If you maintain a space object catalogue and want the checks run against it,
including the private ones, write to fabio@thetesseractacademy.com.
