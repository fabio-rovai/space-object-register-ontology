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
GCAT objects, plus GCAT's `auxcat`, `ftocat` and `satcat100k`:

**Things one catalogue knows and the other does not say**

- **22 entries that GCAT states are not real objects** are still carried by
  CelesTrak. GCAT's own reasons include "Radar error", "Cataloging error" and
  "Delta 150 duplicate".
- **One of those is carried as an on-orbit object.** NORAD 11006 has no decay
  date in CelesTrak, so an entry that GCAT says corresponds to no physical object
  counts as a tracked object still in orbit.
- **1,094 objects GCAT records as no longer tracked** carry no data status code
  in CelesTrak. This is not a missing field. CelesTrak maintains that field and
  uses it on 1,292 other objects, 1,041 as "No Elements Available" and 251 as
  "No Initial Elements". Ten of the GCAT-lost objects are flagged. The other
  1,094 are presented as ordinary on-orbit objects.
- **261 objects on which the two catalogues genuinely disagree** about whether
  the object still exists in orbit. 216 are recorded by GCAT as destroyed or
  returned while CelesTrak publishes no decay date, of which 154 are reentries,
  30 explosions, 14 deorbits and 14 collisions, spread across every decade from
  the 1960s to the 2020s. The remaining 45 run the other way.
- **622 objects** appear in CelesTrak and in none of GCAT's four catalogues.
- **605 objects GCAT tracks have no NORAD number at all.** 334 of them are still
  in orbit, 538 launched since 2020, and 298 are Chinese.
- **Three NORAD numbers are asserted for two different objects inside GCAT**,
  which are candidate defects in GCAT and are reported as such.

**Things neither catalogue can tell you**

- **20,198 of 34,814 on-orbit objects, 58.0 percent, have no published radar
  cross section**, so no size or mass estimate can be derived from the public
  record. A further 618 have no orbital period at all.
- **180 on-orbit objects have an owner recorded as "TBD"** and 53 have an object
  type of "UNK". These are open identifications, not clerical gaps.
- **Attribution is not interoperable between the two catalogues.** Only 42.2
  percent of shared objects carry an identical owner string, and almost all of
  the difference is vocabulary rather than disagreement: CIS against SU and RU,
  PRC against CN, FR against F. Neither register publishes a crosswalk to the
  other. The substantive part is that **CelesTrak's "CIS" collapses the Soviet
  Union and the Russian Federation into a single code**, where GCAT separates
  16,142 Soviet objects from 9,016 Russian ones. That distinction cannot be
  recovered from CelesTrak at all.
- **157 objects are attributed to the United States by CelesTrak and to New
  Zealand by GCAT**, which is the launch state against operator nationality
  question that determines liability under the Registration Convention.

And one finding in the other direction, which matters just as much:

- **All 70,292 CelesTrak COSPAR designators are well formed**, with no
  duplicates and no collisions. We expected to find malformation and there is
  none.

Full method, decomposition, corrections and caveats are in
[BUILD_REPORT.md](BUILD_REPORT.md).

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
