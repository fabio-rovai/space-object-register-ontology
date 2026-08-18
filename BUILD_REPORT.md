# Build report

Built 18 August 2026. Every number below is computed twice, once set-based in
Python from the source files and once by SPARQL over the emitted graph, by
`pipeline/governance_report.py`, which exits non-zero on any disagreement.

## The target changed after source verification

The work began as an ontology for space electronic parts qualification, covering
the ESA qualified parts and preferred parts lists and the US Defense Logistics
Agency qualified products lists. Hands-on verification killed that target. The
structured registers are all gated:

| Source | Result on 18 August 2026 |
|---|---|
| `spacecomponents.org/eppleppl/export` | BLOCKED, OpenAM login |
| `spacecomponents.org/epplcomponent/list` | BLOCKED, same login page byte for byte |
| `spacecomponents.org/epplmanufacturer/list` | BLOCKED, same login page |
| `qpldocs.dla.mil` | BLOCKED, web application firewall returns "Request Rejected" |
| `dla.mil` | HTTP 403 at the edge |
| `escies.org` documents | OPEN and keyless, but documents rather than a structured register |

No access control was circumvented. A parts vertical is still possible once an
ESCIES account exists, and that account is a human action rather than an
automated one.

The build moved to space object catalogues, where two independently maintained
registers of the same physical population are open and keyless.

## Sources actually used

| Source | Licence | Retrieved | Size |
|---|---|---|---|
| CelesTrak SATCAT | Not stated on the site. Pipeline and graph are regenerable and the data is not committed. | 18 Aug 2026 | 70,292 objects |
| GCAT `satcat` | CC BY 4.0, McDowell | 18 Aug 2026, file stamped 12:33 | 69,999 phases, 69,391 numbered objects |
| GCAT `auxcat` | CC BY 4.0 | 18 Aug 2026 | 11,962 phases |
| GCAT `ftocat` | CC BY 4.0 | 18 Aug 2026 | 1,802 phases |

Citation required by the GCAT licence: McDowell, Jonathan C., 2020. General
Catalog of Artificial Space Objects, https://planet4589.org/space/gcat

ESA DISCOS and Space-Track both return HTTP 401. Both offer free accounts, so
they are gated rather than closed, and they are the obvious third and fourth
sources for a later release.

## Two modelling errors caught before they reached a number

**GCAT rows are flight phases, not objects.** The documentation states that each
entry represents "a time period or phase in the flight history of an object" and
that `Status` describes "the event that ends the phase". A first pass that took
one row per object would have mixed first phases and terminal phases. The
pipeline groups every phase of an object before deriving disposition.

**GCAT is not one catalogue.** An early count of objects present in CelesTrak and
absent from GCAT gave 902 against `satcat` alone. Checking `auxcat` and `ftocat`
as well recovered 2 of them, so the published figure is 900. The check mattered
less than expected here, but publishing 902 without running it would have been
luck rather than method.

## Findings

1. **22 catalogue entries that GCAT states are not real objects are still carried
   by CelesTrak.** GCAT's `ERR` status means "no object corresponding to this
   entry (tracking or cataloging errors)". All 22 appear in CelesTrak. GCAT gives
   its own reasons in the entry names, including "Radar error", "Cataloging
   error", "Spurious debris?", "Explorer XXVI dup?" and "Delta 150 duplicate".

2. **One of those 22 is carried as an on-orbit object.** NORAD 11006, which GCAT
   labels "Delta 150 duplicate", has no decay date in CelesTrak and therefore
   counts as a tracked object still in orbit.

3. **1,104 objects that GCAT records as no longer tracked are presented by
   CelesTrak as ordinary on-orbit objects.** GCAT's `OX` status means "in orbit
   (probably) but lost: as O, but no recent tracking data". GCAT applies it to
   1,135 objects, and 1,104 of those have no decay date in CelesTrak and no field
   marking the loss of tracking.

4. **932 objects on which the two catalogues disagree about whether the object is
   still in orbit**, after honest decomposition. The raw disagreement is larger.
   163 objects are recorded as physically gone by GCAT while CelesTrak publishes
   no decay date. 933 carry a CelesTrak decay date while GCAT does not record
   them as gone, and of those, 164 are explained by GCAT recording that the
   object left Earth orbit rather than reentering, which is a different event.
   The unexplained residue in that direction is 769.

5. **900 objects appear in CelesTrak and in none of the three GCAT catalogues.**

6. **605 objects that GCAT tracks have no NORAD number at all**, carried under
   the placeholder `NNA`. They include named payloads such as Mayak and
   Naxing-2.

7. **Three NORAD numbers are asserted for two different objects inside GCAT.**
   These are candidate defects in GCAT rather than in the US catalogue, and two
   of the three share one pattern. JCAT S69898 (GRUS-3E) carries NORAD 66898,
   which belongs to Starlink 36065 at JCAT S66898. JCAT S69903 (Balkan-3)
   carries NORAD 66903, which belongs to Starlink 36077 at JCAT S66903. In both
   cases the JCAT number and the asserted NORAD number differ only in the second
   digit. The third case is JCAT S68468 (DB-BECON-2-VU) carrying NORAD 68488,
   which CelesTrak and JCAT S68488 both give to Vindler 2.1.

## Hypotheses that died

**CelesTrak identifier hygiene is excellent, and we expected otherwise.** All
70,292 COSPAR international designators match the declared pattern, with zero
exceptions. No COSPAR designator is shared by more than one NORAD number, and no
NORAD number is duplicated. Two prior verticals in this family found identifier
malformation in the register they examined. This register has none, and that is
worth stating as plainly as a defect would have been.

The NORAD number itself carries no check digit, so a transcription error produces
another syntactically valid NORAD number. The three GCAT collisions above were
detectable only because GCAT maintains its own independent JCAT identifier
alongside the NORAD number. That is an argument for redundant identifiers rather
than a criticism of either catalogue.

## Verification

Three independent paths, as required.

- `pyshacl` over three SHACL layers, one shape per defect class.
- Our own engine at `~/projects/open-ontologies/target/release/open-ontologies`,
  `validate` on all five ontology files and `lint` on the core.
- Dual computation in `pipeline/governance_report.py`.

The lint reported two informational findings, both that a property carries no
`rdfs:domain`. Both omissions are deliberate, because `space:aboutObject` and
`space:exhibitsDefect` are each used on more than one class, and in OWL
`rdfs:domain` is an inference rather than a constraint, so declaring one class
would cause a reasoner to assert a false type for the other. The reason is now
recorded in the ontology itself rather than silently suppressed.

## Caveats

Both catalogues change daily. Every figure here is a claim about the state of
two files retrieved on 18 August 2026, which is why the model dates every
assertion rather than storing status as a property of an object.

Disposition dates are kept as strings. GCAT deliberately publishes vague dates
such as `1990?` and `2010 Q3?`, and coercing those into `xsd:date` would destroy
the uncertainty the source recorded on purpose.

Neither catalogue is treated here as ground truth. A disagreement between them is
recorded as a disagreement, not as an error in one of them.

## Verification results

The dual-computation gate passes. Every defect count agrees between the
set-based Python path and the SPARQL path:

| Defect class | Python | SPARQL | Agree |
|---|---|---|---|
| PhantomEntry | 22 | 22 | yes |
| PhantomEntryOnOrbit | 1 | 1 | yes |
| UndisclosedTrackingLoss | 1,104 | 1,104 | yes |
| DispositionDisagreement | 932 | 932 | yes |
| CoverageGap | 900 | 900 | yes |
| UnnumberedObject | 605 | 605 | yes |
| IdentifierCollision inside GCAT | 3 | 3 | yes |

`pyshacl` over layer 3 returns 3,564 results, which is the sum of the six
cross-source defect classes above. The validation report is the findings table,
which is the property the layering was designed for.

## A finding about our own tooling

The full graph is 2,330,660 triples in 88.2 MB of Turtle. Emitting it as text
takes 8 seconds. Reading it back is where the cost sits:

| Engine | Result |
|---|---|
| `open-ontologies` (Rust) | 2,330,660 triples loaded in 66 seconds |
| `rdflib` 7.6.0 | same 2,330,660 triples, over an hour, about 4.97 GB resident |

**Correction, made after this report was first written.** The first version of
this section said the rdflib run had been killed at 55 minutes and had not
finished. That was wrong. The run completed and its result is the one recorded
in the verification table above, computed over the full graph rather than over
any subset. The error was ours: the process was assumed dead because it was
still parsing when checked at 55 minutes, and a kill was issued that did not
take effect before it finished. The engine comparison stands, because 66 seconds
against more than an hour is the same conclusion, but the claim that rdflib
could not complete the parse was not true and the corrected figure is above.

This still extends what we already knew about rdflib at scale. The recorded
limit was that multi-way self-joins over reified nodes time out while parsing
and serialising remain usable. At 2.3M triples parsing remains possible but
costs roughly sixty times what the Rust engine costs, and about 5 GB of memory.

Two limitations in our own engine surfaced while working around this, and both
are ours to fix rather than to write around quietly. `load` and `query` do not
share an in-memory store across separate process invocations, and `batch` cannot
run SPARQL, which is already filed as open-ontologies issue 100. Together they
mean the fast loader cannot currently be used for the verification query in one
pass.

`pipeline/build_graph.py` also emits a defect subgraph of 11,142 triples, which
parses in 3.1 seconds and contains every node the findings depend on. That is a
convenience for fast iteration. It is not what the published numbers rest on:
those come from the full graph.
