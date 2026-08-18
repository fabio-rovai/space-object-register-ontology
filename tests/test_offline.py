"""Offline tests. No network. Fixtures are inline so CI never fetches."""
import re, sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "pipeline"))
ONT = pathlib.Path(__file__).resolve().parent.parent / "ontology"

COSPAR = re.compile(r"^[0-9]{4}-[0-9]{3}[A-Z]{1,3}$")
NORAD = re.compile(r"^[0-9]{1,6}$")


class TestSchemePatterns(unittest.TestCase):
    """The declared patterns must behave as the ontology claims."""

    def test_cospar_accepts_real_designators(self):
        for v in ["1957-001A", "2026-123ABC", "1998-067A"]:
            self.assertTrue(COSPAR.match(v), v)

    def test_cospar_rejects_malformed(self):
        for v in ["57-001A", "1957-1A", "1957-001", "1957-001a", ""]:
            self.assertFalse(COSPAR.match(v), v)

    def test_norad_has_no_check_digit(self):
        """A single digit change yields another valid NORAD number.

        This is the property that makes the three GCAT collisions undetectable
        inside the NORAD scheme alone.
        """
        self.assertTrue(NORAD.match("66898"))
        self.assertTrue(NORAD.match("69898"))


class TestStatusSemantics(unittest.TestCase):
    """Status classification must not conflate reentry with leaving Earth orbit."""

    def test_gone_and_left_earth_are_disjoint(self):
        from reconcile import DESTROYED, LEFT_EARTH, ERROR, LOST
        self.assertEqual(DESTROYED & LEFT_EARTH, set())
        self.assertIn("R", DESTROYED)
        self.assertIn("D", DESTROYED)
        self.assertIn("DSO", LEFT_EARTH)
        self.assertIn("ERR", ERROR)
        self.assertIn("OX", LOST)

    def test_destruction_codes_are_not_in_orbit(self):
        """Regression for the error that inflated disagreement by 3.6x.

        E and C destroy the object. They were originally classified as
        "still in orbit", which is what produced the wrong 932.
        """
        from reconcile import DESTROYED, INORBIT
        self.assertIn("E", DESTROYED)
        self.assertIn("C", DESTROYED)
        self.assertEqual(DESTROYED & INORBIT, set())

    def test_transitions_are_not_disposition_claims(self):
        """Docking and attachment end a phase without ending the object."""
        from reconcile import TRANSITION, DESTROYED, INORBIT, LEFT_EARTH
        for code in ("DK", "ATT", "TFR", "GRP"):
            self.assertIn(code, TRANSITION)
        self.assertEqual(TRANSITION & (DESTROYED | INORBIT | LEFT_EARTH), set())

    def test_uncertainty_marker_is_stripped(self):
        from reconcile import norm_status, DESTROYED
        self.assertIn(norm_status("R?"), DESTROYED)
        self.assertIn(norm_status("L?"), DESTROYED)

    def test_all_four_gcat_catalogues_are_harvested(self):
        """satcat100k was missed once and moved the coverage gap by 280."""
        from reconcile import CATALOGUES
        self.assertIn("gcat_satcat100k.tsv", CATALOGUES)
        self.assertEqual(len(CATALOGUES), 4)

    def test_err_is_not_a_disposition(self):
        """An error entry is not 'gone'; it never existed."""
        from reconcile import GONE, ERROR
        self.assertEqual(GONE & ERROR, set())


class TestKnownAnswer(unittest.TestCase):
    """Known-answer cases, held from the 18 August 2026 harvest."""

    def test_known_phantom_on_orbit(self):
        """NORAD 11006 is the one phantom carried with no decay date."""
        self.assertTrue(NORAD.match("11006"))

    def test_known_gcat_collision_pattern(self):
        """Two of three collisions differ from their JCAT only in digit two."""
        for jcat, norad in [("69898", "66898"), ("69903", "66903")]:
            diffs = [i for i, (a, b) in enumerate(zip(jcat, norad)) if a != b]
            self.assertEqual(diffs, [1], f"{jcat} vs {norad}")


class TestOntologyFiles(unittest.TestCase):
    def test_all_files_parse(self):
        import rdflib
        for f in sorted(ONT.glob("*.ttl")):
            g = rdflib.Graph()
            g.parse(f, format="turtle")
            self.assertGreater(len(g), 0, f.name)

    def test_no_em_dashes_in_outward_text(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        for f in [root / "README.md", root / "BUILD_REPORT.md", *ONT.glob("*.ttl")]:
            self.assertNotIn("—", f.read_text(), f"em dash in {f.name}")

    def test_defect_classes_have_shapes(self):
        shapes = (ONT / "shapes-layer3-crosssource.ttl").read_text()
        for cls in ["PhantomEntry", "PhantomEntryOnOrbit", "UndisclosedTrackingLoss",
                    "DispositionDisagreement", "CoverageGap", "UnnumberedObject"]:
            self.assertIn(cls, shapes, cls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
